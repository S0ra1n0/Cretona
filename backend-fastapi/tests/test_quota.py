from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.quota_service import NOT_CHARGED, QuotaService
from tests.conftest import USER_A

HEADERS = {"X-Debug-User-Id": USER_A}


@pytest.fixture
def quota_client(tmp_path: Path) -> Iterator[TestClient]:
    media = tmp_path / "media"
    media.mkdir()
    (media / "demo-output.mp4").write_bytes(b"test-mp4-bytes")
    settings = Settings(
        environment="test",
        auth_mode="dev",
        database_path=tmp_path / "quota.db",
        media_dir=media,
        prompt_llm_provider="deterministic",
        fake_polls_before_complete=1,
        generation_quota_limit=2,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client


def create(client: TestClient, prompt: str = "a lantern") -> int:
    return client.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": prompt}
    ).status_code


def drive_to_failure(client: TestClient, prompt: str) -> str:
    created = client.post("/api/v1/projects", headers=HEADERS, json={"prompt": prompt}).json()
    client.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)
    client.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)
    return created["id"]


# --- enforcement ------------------------------------------------------------


def test_quota_blocks_once_the_allowance_is_spent(quota_client: TestClient) -> None:
    assert create(quota_client) == 201
    assert create(quota_client) == 201

    third = quota_client.post("/api/v1/projects", headers=HEADERS, json={"prompt": "one more"})

    assert third.status_code == 429
    assert third.json()["error"]["code"] == "QUOTA_EXCEEDED"


def test_the_refusal_says_what_the_limit_is_and_when_it_lifts(
    quota_client: TestClient,
) -> None:
    create(quota_client)
    create(quota_client)

    message = quota_client.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "blocked"}
    ).json()["error"]["message"]

    assert "all 2 generations" in message
    assert "available at" in message


def test_quota_is_per_user(quota_client: TestClient) -> None:
    create(quota_client)
    create(quota_client)

    other = quota_client.post(
        "/api/v1/projects",
        headers={"X-Debug-User-Id": "20000000-0000-4000-8000-000000000002"},
        json={"prompt": "mine"},
    )

    assert other.status_code == 201


def test_quota_is_checked_before_the_provider_is_called(quota_client: TestClient) -> None:
    create(quota_client)
    create(quota_client)

    quota_client.post("/api/v1/projects", headers=HEADERS, json={"prompt": "blocked"})

    # Checking after the call would be accounting, not control: a refused
    # request must leave no project behind at all.
    listed = quota_client.get("/api/v1/projects", headers=HEADERS).json()
    assert len(listed["items"]) == 2


# --- what counts ------------------------------------------------------------


@pytest.mark.parametrize("failure", NOT_CHARGED)
def test_infrastructure_failures_do_not_consume_an_allowance(
    quota_client: TestClient,
    failure: str,
) -> None:
    drive_to_failure(quota_client, f"fail:{failure} not the user's fault")
    create(quota_client)

    # Two projects exist, but only one was charged.
    assert create(quota_client) == 201


def test_a_rejected_prompt_still_counts(quota_client: TestClient) -> None:
    # The provider call was made and billed, so content_policy is charged.
    drive_to_failure(quota_client, "fail:content_policy unsafe")
    create(quota_client)

    blocked = quota_client.post("/api/v1/projects", headers=HEADERS, json={"prompt": "third"})

    assert blocked.status_code == 429


def test_deleting_a_project_frees_its_allowance(quota_client: TestClient) -> None:
    created = quota_client.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "first"}
    ).json()
    create(quota_client)

    quota_client.delete(f"/api/v1/projects/{created['id']}", headers=HEADERS)

    assert create(quota_client) == 201


def test_retry_costs_an_allowance(quota_client: TestClient) -> None:
    project_id = drive_to_failure(quota_client, "fail:content_policy unsafe")

    # That create used one of two. The retry should claim the second and the
    # attempt after it should be refused.
    retried = quota_client.post(f"/api/v1/projects/{project_id}/retry", headers=HEADERS)
    assert retried.status_code == 409  # content_policy is not retryable

    create(quota_client)
    assert quota_client.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "third"}
    ).status_code == 429


# --- window arithmetic ------------------------------------------------------


class FakeDatabase:
    def __init__(self, used: int, oldest: str | None) -> None:
        self.used = used
        self.oldest = oldest
        self.since: str | None = None

    def count_quota_usage(
        self,
        owner_id: str,
        since: str,
        not_charged: tuple[str, ...],
    ) -> tuple[int, str | None]:
        del owner_id, not_charged
        self.since = since
        return self.used, self.oldest


def build(used: int, oldest: str | None, limit: int = 10) -> tuple[QuotaService, FakeDatabase]:
    database = FakeDatabase(used, oldest)
    settings = Settings(generation_quota_limit=limit, generation_quota_window_hours=24)
    return QuotaService(database, settings), database


def test_reset_time_follows_the_oldest_counted_generation() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    oldest = (now - timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    service, _ = build(used=3, oldest=oldest)

    quota = service.get(USER_A, now)

    # A slot frees 24h after the oldest counted generation, not 24h from now.
    assert quota.resets_at.startswith("2026-08-13T06:00")
    assert quota.remaining == 7


def test_an_unused_quota_reports_a_full_window_ahead() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    service, _ = build(used=0, oldest=None)

    quota = service.get(USER_A, now)

    assert quota.resets_at.startswith("2026-08-13T12:00")
    assert quota.used == 0
    assert quota.remaining == 10


def test_remaining_never_goes_negative() -> None:
    service, _ = build(used=99, oldest=None, limit=10)

    assert service.get(USER_A).remaining == 0


def test_the_window_start_is_passed_to_the_database() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    service, database = build(used=0, oldest=None)

    service.get(USER_A, now)

    assert database.since == "2026-08-11T12:00:00Z"
