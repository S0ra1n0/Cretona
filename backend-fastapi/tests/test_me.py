from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import USER_A, USER_B

HEADERS = {"X-Debug-User-Id": USER_A}
OTHER = {"X-Debug-User-Id": USER_B}


@pytest.fixture
def profiled(client: TestClient) -> TestClient:
    database = client.app.state.database
    database.upsert_user(
        USER_A, email="alice@example.com", username="alice",
        created_at="2026-01-02T00:00:00Z",
    )
    database.upsert_user(USER_B, email="bob@example.com", username="bob")
    return client


def test_profile_reports_identity_and_quota(profiled: TestClient) -> None:
    body = profiled.get("/api/v1/me", headers=HEADERS).json()

    assert body["id"] == USER_A
    assert body["email"] == "alice@example.com"
    assert body["username"] == "alice"
    assert body["role"] == "user"
    assert body["isDisabled"] is False
    assert body["quota"]["limit"] == 10
    assert body["quota"]["used"] == 0
    assert body["quota"]["remaining"] == 10
    assert body["quota"]["resetsAt"].endswith("Z")


def test_quota_usage_is_reflected(profiled: TestClient) -> None:
    profiled.post("/api/v1/projects", headers=HEADERS, json={"prompt": "one"})
    profiled.post("/api/v1/projects", headers=HEADERS, json={"prompt": "two"})

    quota = profiled.get("/api/v1/me", headers=HEADERS).json()["quota"]

    assert quota["used"] == 2
    assert quota["remaining"] == 8


def test_quota_shown_is_the_callers_own(profiled: TestClient) -> None:
    profiled.post("/api/v1/projects", headers=HEADERS, json={"prompt": "mine"})

    assert profiled.get("/api/v1/me", headers=OTHER).json()["quota"]["used"] == 0


def test_profile_requires_authentication(supabase_client: TestClient) -> None:
    assert supabase_client.get("/api/v1/me").status_code == 401


def test_missing_profile_is_not_found(client: TestClient) -> None:
    # Dev mode injects an identity without requiring a row to exist.
    assert client.get("/api/v1/me", headers=HEADERS).status_code == 404


# --- updating ---------------------------------------------------------------


def test_username_can_be_changed(profiled: TestClient) -> None:
    response = profiled.patch("/api/v1/me", headers=HEADERS, json={"username": "alice_2"})

    assert response.status_code == 200
    assert response.json()["username"] == "alice_2"
    assert profiled.get("/api/v1/me", headers=HEADERS).json()["username"] == "alice_2"


def test_taken_username_is_a_conflict(profiled: TestClient) -> None:
    response = profiled.patch("/api/v1/me", headers=HEADERS, json={"username": "bob"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_keeping_your_own_username_is_not_a_conflict(profiled: TestClient) -> None:
    assert profiled.patch(
        "/api/v1/me", headers=HEADERS, json={"username": "alice"}
    ).status_code == 200


@pytest.mark.parametrize(
    "username",
    ["ab", "a" * 31, "has space", "has-dash", "emoji_\U0001f600", ""],
)
def test_invalid_usernames_are_rejected(profiled: TestClient, username: str) -> None:
    response = profiled.patch("/api/v1/me", headers=HEADERS, json={"username": username})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_role_cannot_be_changed_through_the_profile(profiled: TestClient) -> None:
    profiled.patch(
        "/api/v1/me",
        headers=HEADERS,
        json={"username": "alice_3", "role": "admin", "isDisabled": True},
    )

    body = profiled.get("/api/v1/me", headers=HEADERS).json()

    # Extra fields are ignored, not applied: privilege is an admin decision.
    assert body["role"] == "user"
    assert body["isDisabled"] is False
