from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import AppError
from app.main import create_app
from app.schemas import AdminUserUpdate
from app.storage import MAX_IMAGE_BYTES, read_bounded
from tests.conftest import USER_A, USER_B

ADMIN_ID = "30000000-0000-4000-8000-000000000003"
SECOND_ADMIN = "40000000-0000-4000-8000-000000000004"
ADMIN_HEADERS = {"X-Debug-User-Id": ADMIN_ID}
HEADERS = {"X-Debug-User-Id": USER_A}


# --- generation timeout -----------------------------------------------------


@pytest.fixture
def impatient(tmp_path: Path) -> Iterator[TestClient]:
    media = tmp_path / "media"
    media.mkdir()
    (media / "demo-output.mp4").write_bytes(b"test-mp4-bytes")
    settings = Settings(
        environment="test",
        auth_mode="dev",
        database_path=tmp_path / "timeout.db",
        media_dir=media,
        prompt_llm_provider="deterministic",
        # A prompt starting with "slow" needs three polls; this expires first.
        generation_timeout_seconds=30,
        poller_enabled=False,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client


def age_project(client: TestClient, project_id: str, moment: str) -> None:
    """Backdate both clocks, so a test cannot pass on the wrong one."""
    with client.app.state.database.connect() as connection:
        connection.execute(
            "UPDATE projects SET created_at = ?, started_at = ? WHERE id = ?",
            (moment, moment, project_id),
        )


def started_at(client: TestClient, project_id: str) -> str | None:
    return client.app.state.database.get_project(project_id, USER_A)["started_at"]


def test_a_stuck_generation_eventually_fails(impatient: TestClient) -> None:
    created = impatient.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "slow one"}
    ).json()
    impatient.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)

    # The provider accepted the job and then went quiet.
    age_project(impatient, created["id"], "2020-01-01T00:00:00Z")
    body = impatient.get(f"/api/v1/projects/{created['id']}", headers=HEADERS).json()

    assert body["status"] == "failed"
    assert body["errorMessage"] == "Video generation took too long. Please retry later."


def test_a_timed_out_generation_can_be_retried(impatient: TestClient) -> None:
    created = impatient.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "slow one"}
    ).json()
    impatient.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)
    age_project(impatient, created["id"], "2020-01-01T00:00:00Z")
    impatient.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)

    # A timeout was not the user's fault, so it stays retryable.
    retried = impatient.post(f"/api/v1/projects/{created['id']}/retry", headers=HEADERS)

    assert retried.status_code == 202


def test_a_retry_gets_a_fresh_timeout_budget(impatient: TestClient) -> None:
    """The bug B-1 exists to fix.

    Measuring from created_at meant a project created long ago and retried a
    moment ago was failed as timed out on its very next read, which makes
    retry useless for exactly the transient failures it is meant to handle.
    """
    created = impatient.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "slow one"}
    ).json()
    impatient.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)
    age_project(impatient, created["id"], "2020-01-01T00:00:00Z")
    impatient.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)

    impatient.post(f"/api/v1/projects/{created['id']}/retry", headers=HEADERS)
    body = impatient.get(f"/api/v1/projects/{created['id']}", headers=HEADERS).json()

    # Still in flight: the old creation date no longer condemns it.
    assert body["status"] == "generating"


def test_the_attempt_clock_is_set_on_submit_and_reset_on_retry(
    impatient: TestClient,
) -> None:
    created = impatient.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "slow one"}
    ).json()
    first = started_at(impatient, created["id"])
    assert first is not None

    age_project(impatient, created["id"], "2020-01-01T00:00:00Z")
    impatient.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)
    impatient.post(f"/api/v1/projects/{created['id']}/retry", headers=HEADERS)

    assert started_at(impatient, created["id"]) > "2020-01-01T00:00:00Z"


def test_a_row_without_an_attempt_clock_falls_back_to_created_at(
    impatient: TestClient,
) -> None:
    """Rows written before migration 004 have no started_at."""
    created = impatient.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "slow one"}
    ).json()
    impatient.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)

    with impatient.app.state.database.connect() as connection:
        connection.execute(
            "UPDATE projects SET started_at = NULL, created_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00Z", created["id"]),
        )

    body = impatient.get(f"/api/v1/projects/{created['id']}", headers=HEADERS).json()

    # Falls back rather than being read as "started at the epoch".
    assert body["status"] == "failed"
    assert body["errorMessage"] == "Video generation took too long. Please retry later."


def test_a_fresh_generation_is_not_timed_out(impatient: TestClient) -> None:
    created = impatient.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "slow one"}
    ).json()

    body = impatient.get(f"/api/v1/projects/{created['id']}", headers=HEADERS).json()

    assert body["status"] == "generating"


def test_the_poller_sweeps_stuck_projects(impatient: TestClient) -> None:
    created = impatient.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "slow one"}
    ).json()
    age_project(impatient, created["id"], "2020-01-01T00:00:00Z")

    impatient.app.state.poller.run_once()

    row = impatient.app.state.database.get_project(created["id"], USER_A)
    assert row["status"] == "failed"
    assert row["error_code"] == "timeout"
    # And it is not claimed again on the next pass.
    assert impatient.app.state.poller.run_once() == 0


def test_a_completed_project_is_never_timed_out(impatient: TestClient) -> None:
    created = impatient.post("/api/v1/projects", headers=HEADERS, json={"prompt": "quick"}).json()
    impatient.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)
    impatient.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)
    age_project(impatient, created["id"], "2020-01-01T00:00:00Z")

    body = impatient.get(f"/api/v1/projects/{created['id']}", headers=HEADERS).json()

    assert body["status"] == "completed"


# --- last admin -------------------------------------------------------------


@pytest.fixture
def admins(client: TestClient) -> TestClient:
    database = client.app.state.database
    database.upsert_user(ADMIN_ID, email="admin@example.com", role="admin")
    database.upsert_user(USER_A, email="alice@example.com", username="alice")
    return client


def test_self_modification_is_what_protects_the_last_admin(admins: TestClient) -> None:
    """The HTTP-level guarantee, stated as a test rather than assumed.

    With one admin left, the only request that could strip the last privilege
    is that admin acting on themselves, and that is refused.
    """
    assert admins.app.state.database.count_enabled_admins() == 1

    demote = admins.patch(
        f"/api/v1/admin/users/{ADMIN_ID}", headers=ADMIN_HEADERS, json={"role": "user"}
    )
    disable = admins.patch(
        f"/api/v1/admin/users/{ADMIN_ID}", headers=ADMIN_HEADERS, json={"isDisabled": True}
    )

    assert demote.status_code == 403
    assert disable.status_code == 403
    assert admins.app.state.database.count_enabled_admins() == 1


def test_a_non_admin_actor_cannot_reach_the_endpoint_at_all(admins: TestClient) -> None:
    # The other half of why the service-level guard is unreachable over HTTP.
    response = admins.patch(
        f"/api/v1/admin/users/{ADMIN_ID}",
        headers={"X-Debug-User-Id": USER_A},
        json={"role": "user"},
    )

    assert response.status_code == 403


def test_the_service_refuses_to_strip_the_last_admin(admins: TestClient) -> None:
    """Exercised directly, because the API path cannot produce this state.

    AdminService is a plain object a script could call without the role gate,
    so the invariant is enforced there too.
    """
    service = admins.app.state.admin_service
    assert admins.app.state.database.count_enabled_admins() == 1

    with pytest.raises(AppError) as demoted:
        service.update_user("someone-else", ADMIN_ID, AdminUserUpdate(role="user"))

    with pytest.raises(AppError) as disabled:
        service.update_user("someone-else", ADMIN_ID, AdminUserUpdate(isDisabled=True))

    assert demoted.value.status_code == 409
    assert disabled.value.status_code == 409
    assert "last enabled admin" in demoted.value.message
    assert admins.app.state.database.count_enabled_admins() == 1


def test_the_service_allows_it_once_a_second_admin_exists(admins: TestClient) -> None:
    admins.app.state.database.upsert_user(SECOND_ADMIN, email="second@example.com", role="admin")
    service = admins.app.state.admin_service

    result = service.update_user("someone-else", ADMIN_ID, AdminUserUpdate(role="user"))

    assert result.role == "user"


def test_promoting_is_never_blocked(admins: TestClient) -> None:
    response = admins.patch(
        f"/api/v1/admin/users/{USER_A}", headers=ADMIN_HEADERS, json={"role": "admin"}
    )

    assert response.status_code == 200


def test_disabling_a_non_admin_is_never_blocked(admins: TestClient) -> None:
    response = admins.patch(
        f"/api/v1/admin/users/{USER_A}", headers=ADMIN_HEADERS, json={"isDisabled": True}
    )

    assert response.status_code == 200


def test_admin_changes_are_logged(
    admins: TestClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    admins.patch(f"/api/v1/admin/users/{USER_A}", headers=ADMIN_HEADERS, json={"role": "admin"})

    captured = capsys.readouterr().out

    assert "admin_user_updated" in captured
    assert ADMIN_ID in captured
    assert USER_A in captured


# --- weighted retry cost (R-2) ----------------------------------------------


@pytest.fixture
def tight_quota(tmp_path: Path) -> Iterator[TestClient]:
    media = tmp_path / "media"
    media.mkdir()
    (media / "demo-output.mp4").write_bytes(b"test-mp4-bytes")
    settings = Settings(
        environment="test",
        auth_mode="dev",
        database_path=tmp_path / "weighted.db",
        media_dir=media,
        prompt_llm_provider="deterministic",
        generation_quota_limit=2,
        poller_enabled=False,
        generation_log_retention_enabled=False,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client


def spend_one_unit(client: TestClient) -> None:
    """Consume exactly one charged unit with a completed fake generation."""
    other = client.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "cheap", "provider": "fake"}
    ).json()
    for _ in range(2):
        client.get(f"/api/v1/projects/{other['id']}", headers=HEADERS)


def failed_project(client: TestClient, provider: str) -> str:
    # provider_error is retryable and, being our fault, is not charged -- so
    # the failed row itself contributes nothing to usage.
    created = client.post(
        "/api/v1/projects",
        headers=HEADERS,
        json={"prompt": "fail:provider_error down", "provider": provider},
    ).json()
    for _ in range(2):
        client.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)
    return created["id"]


def test_a_weighted_retry_cannot_exceed_the_quota(tight_quota: TestClient) -> None:
    """The bug R-2 fixes.

    create charged the weighted cost while retry charged a flat 1, so a 2-unit
    wan21 retry was admitted with only 1 unit left of a limit of 2.
    """
    project_id = failed_project(tight_quota, "wan21")
    spend_one_unit(tight_quota)

    refused = tight_quota.post(f"/api/v1/projects/{project_id}/retry", headers=HEADERS)

    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "QUOTA_EXCEEDED"


def test_an_unweighted_retry_still_fits(tight_quota: TestClient) -> None:
    # Same remaining allowance, but a fake retry costs 1 rather than 2.
    project_id = failed_project(tight_quota, "fake")
    spend_one_unit(tight_quota)

    assert (
        tight_quota.post(f"/api/v1/projects/{project_id}/retry", headers=HEADERS).status_code == 202
    )


# --- bounded upload (R-3) ---------------------------------------------------


class CountingUpload:
    """An upload that reports how much was actually pulled from it."""

    def __init__(self, total: int) -> None:
        self.remaining = total
        self.served = 0

    async def read(self, size: int) -> bytes:
        if self.remaining <= 0:
            return b""
        served = min(size, self.remaining)
        self.remaining -= served
        self.served += served
        return b"x" * served


def test_read_bounded_stops_instead_of_materialising_the_body() -> None:
    """The property R-3 adds.

    The old code read everything and then checked the length, so the limit
    bounded the response but not the resources spent producing it. Asserting
    the 413 alone would pass either way; this asserts we stopped reading.
    """
    upload = CountingUpload(MAX_IMAGE_BYTES * 4)

    with pytest.raises(AppError) as caught:
        asyncio.run(read_bounded(upload, MAX_IMAGE_BYTES))

    assert caught.value.status_code == 413
    # One chunk past the limit, not the whole 40 MB.
    assert upload.served <= MAX_IMAGE_BYTES + 64 * 1024


def test_read_bounded_returns_a_body_within_the_limit() -> None:
    upload = CountingUpload(1024)

    assert asyncio.run(read_bounded(upload, MAX_IMAGE_BYTES)) == b"x" * 1024


def test_an_oversized_upload_is_refused(client: TestClient) -> None:
    payload = b"x" * (MAX_IMAGE_BYTES + 1024)

    response = client.post(
        "/api/v1/uploads",
        headers=HEADERS,
        files={"file": ("big.png", payload, "image/png")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_an_unsupported_upload_type_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/v1/uploads",
        headers=HEADERS,
        files={"file": ("x.svg", b"<svg/>", "image/svg+xml")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["issue"] == "unsupported_type"


def test_a_missing_content_type_is_not_treated_as_a_jpeg(client: TestClient) -> None:
    response = client.post(
        "/api/v1/uploads",
        headers=HEADERS,
        files={"file": ("x.bin", b"data", "application/octet-stream")},
    )

    assert response.status_code == 400


def test_a_valid_upload_still_works(client: TestClient) -> None:
    response = client.post(
        "/api/v1/uploads",
        headers=HEADERS,
        files={"file": ("small.png", b"png-bytes", "image/png")},
    )

    assert response.status_code == 201
    assert response.json()["storagePath"].startswith(f"{USER_A}/")


# --- releasing a username ---------------------------------------------------


def test_a_username_can_be_released(admins: TestClient) -> None:
    cleared = admins.patch("/api/v1/me", headers=HEADERS, json={"username": None})

    assert cleared.status_code == 200
    assert cleared.json()["username"] is None


def test_a_released_username_becomes_available(admins: TestClient) -> None:
    admins.app.state.database.upsert_user(USER_B, email="bob@example.com")
    admins.patch("/api/v1/me", headers=HEADERS, json={"username": None})

    taken = admins.patch(
        "/api/v1/me",
        headers={"X-Debug-User-Id": USER_B},
        json={"username": "alice"},
    )

    assert taken.status_code == 200
    assert taken.json()["username"] == "alice"
