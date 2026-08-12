from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import AppError
from app.main import create_app
from app.schemas import AdminUserUpdate
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


def age_project(client: TestClient, project_id: str, created_at: str) -> None:
    with client.app.state.database.connect() as connection:
        connection.execute(
            "UPDATE projects SET created_at = ? WHERE id = ?",
            (created_at, project_id),
        )


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
    created = impatient.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "quick"}
    ).json()
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
    admins.app.state.database.upsert_user(
        SECOND_ADMIN, email="second@example.com", role="admin"
    )
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
    admins.patch(
        f"/api/v1/admin/users/{USER_A}", headers=ADMIN_HEADERS, json={"role": "admin"}
    )

    captured = capsys.readouterr().out

    assert "admin_user_updated" in captured
    assert ADMIN_ID in captured
    assert USER_A in captured


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
