from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.rate_limit import RateLimiter, bucket_for, caller_key
from tests.conftest import USER_A, USER_B

HEADERS = {"X-Debug-User-Id": USER_A}
OTHER = {"X-Debug-User-Id": USER_B}


@pytest.fixture
def limited(tmp_path: Path) -> Iterator[TestClient]:
    media = tmp_path / "media"
    media.mkdir()
    (media / "demo-output.mp4").write_bytes(b"test-mp4-bytes")
    settings = Settings(
        environment="test",
        auth_mode="dev",
        database_path=tmp_path / "rl.db",
        media_dir=media,
        prompt_llm_provider="deterministic",
        fake_polls_before_complete=1,
        rate_limit_default_per_min=3,
        rate_limit_generation_per_min=2,
        poller_enabled=False,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client


# --- unit -------------------------------------------------------------------


def test_window_allows_up_to_the_limit_then_refuses() -> None:
    limiter = RateLimiter(default_per_minute=2, generation_per_minute=1)

    assert limiter.check("k", "default", now=0.0)[0] is True
    assert limiter.check("k", "default", now=0.1)[0] is True
    assert limiter.check("k", "default", now=0.2)[0] is False


def test_hits_age_out_of_the_window() -> None:
    limiter = RateLimiter(default_per_minute=1, generation_per_minute=1)

    assert limiter.check("k", "default", now=0.0)[0] is True
    assert limiter.check("k", "default", now=30.0)[0] is False
    # 60s after the first hit, the slot is free again.
    assert limiter.check("k", "default", now=60.1)[0] is True


def test_buckets_and_keys_are_independent() -> None:
    limiter = RateLimiter(default_per_minute=1, generation_per_minute=1)
    limiter.check("a", "default", now=0.0)

    assert limiter.check("a", "generation", now=0.0)[0] is True
    assert limiter.check("b", "default", now=0.0)[0] is True


def test_remaining_counts_down() -> None:
    limiter = RateLimiter(default_per_minute=3, generation_per_minute=1)

    assert limiter.check("k", "default", now=0.0) == (True, 3, 2)
    assert limiter.check("k", "default", now=0.1) == (True, 3, 1)
    assert limiter.check("k", "default", now=0.2) == (True, 3, 0)


def test_generation_writes_get_the_tighter_bucket() -> None:
    assert bucket_for("POST", "/api/v1/projects") == "generation"
    assert bucket_for("POST", "/api/v1/projects/abc/retry") == "generation"
    # Reads are not generation, whatever the path.
    assert bucket_for("GET", "/api/v1/projects") == "default"
    assert bucket_for("POST", "/api/v1/me") == "default"


def test_the_token_is_hashed_not_stored() -> None:
    key = caller_key("Bearer secret-token-value", None, "1.2.3.4")

    assert "secret-token-value" not in key
    assert key.startswith("t:")


def test_callers_are_distinguished_by_the_best_signal_available() -> None:
    assert caller_key("Bearer a", USER_A, "1.1.1.1") != caller_key("Bearer b", USER_A, "1.1.1.1")
    assert caller_key(None, USER_A, "1.1.1.1") != caller_key(None, USER_B, "1.1.1.1")
    assert caller_key(None, None, "1.1.1.1") != caller_key(None, None, "2.2.2.2")


# --- integration ------------------------------------------------------------


def test_reads_are_limited_and_report_the_headers(limited: TestClient) -> None:
    first = limited.get("/api/v1/projects", headers=HEADERS)

    assert first.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "3"
    assert first.headers["X-RateLimit-Remaining"] == "2"

    limited.get("/api/v1/projects", headers=HEADERS)
    limited.get("/api/v1/projects", headers=HEADERS)
    refused = limited.get("/api/v1/projects", headers=HEADERS)

    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "RATE_LIMITED"
    assert refused.headers["Retry-After"] == "60"
    assert refused.headers["X-RateLimit-Remaining"] == "0"


def test_generation_has_a_tighter_budget_than_reads(limited: TestClient) -> None:
    assert limited.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "one"}
    ).status_code == 201
    assert limited.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "two"}
    ).status_code == 201

    third = limited.post("/api/v1/projects", headers=HEADERS, json={"prompt": "three"})

    assert third.status_code == 429
    assert third.headers["X-RateLimit-Limit"] == "2"


def test_one_caller_cannot_exhaust_anothers_budget(limited: TestClient) -> None:
    for _ in range(3):
        limited.get("/api/v1/projects", headers=HEADERS)

    assert limited.get("/api/v1/projects", headers=HEADERS).status_code == 429
    assert limited.get("/api/v1/projects", headers=OTHER).status_code == 200


def test_refusal_still_carries_the_correlation_id(limited: TestClient) -> None:
    for _ in range(4):
        response = limited.get(
            "/api/v1/projects", headers={**HEADERS, "X-Request-ID": "trace"}
        )

    assert response.status_code == 429
    assert response.headers["X-Request-ID"] == "trace"
    assert response.json()["requestId"] == "trace"


def test_health_is_never_rate_limited(limited: TestClient) -> None:
    # A liveness probe that can be throttled reports an outage that is not one.
    for _ in range(10):
        assert limited.get("/api/v1/health").status_code == 200


def test_limiting_can_be_switched_off(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    settings = Settings(
        environment="test",
        database_path=tmp_path / "off.db",
        media_dir=media,
        rate_limit_enabled=False,
        rate_limit_default_per_min=1,
        poller_enabled=False,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        for _ in range(5):
            response = client.get("/api/v1/projects", headers=HEADERS)

    assert response.status_code == 200
    assert "X-RateLimit-Limit" not in response.headers
