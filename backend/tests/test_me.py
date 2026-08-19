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
        USER_A,
        email="alice@example.com",
        username="alice",
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
    assert (
        profiled.patch("/api/v1/me", headers=HEADERS, json={"username": "alice"}).status_code == 200
    )


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


# --- optional profile details (gender / birthday) ---------------------------


def test_details_are_null_until_the_account_chooses_them(profiled: TestClient) -> None:
    body = profiled.get("/api/v1/me", headers=HEADERS).json()

    # Only the username is required to finish setup, so an account that has
    # not answered reads as null rather than as an empty string.
    assert body["gender"] is None
    assert body["birthday"] is None


def test_details_are_saved_and_returned(profiled: TestClient) -> None:
    response = profiled.patch(
        "/api/v1/me",
        headers=HEADERS,
        json={"username": "alice", "gender": "female", "birthday": "1998-04-17"},
    )

    assert response.status_code == 200
    assert response.json()["gender"] == "female"
    assert response.json()["birthday"] == "1998-04-17"

    body = profiled.get("/api/v1/me", headers=HEADERS).json()
    assert body["gender"] == "female"
    assert body["birthday"] == "1998-04-17"


def test_gender_is_stored_lowercase(profiled: TestClient) -> None:
    body = profiled.patch(
        "/api/v1/me",
        headers=HEADERS,
        json={"username": "alice", "gender": "Male"},
    ).json()

    assert body["gender"] == "male"


def test_omitted_details_are_left_alone(profiled: TestClient) -> None:
    profiled.patch(
        "/api/v1/me",
        headers=HEADERS,
        json={"username": "alice", "gender": "other", "birthday": "2000-01-01"},
    )

    # A rename that says nothing about the details must not wipe them.
    profiled.patch("/api/v1/me", headers=HEADERS, json={"username": "alice_2"})

    body = profiled.get("/api/v1/me", headers=HEADERS).json()
    assert body["gender"] == "other"
    assert body["birthday"] == "2000-01-01"


def test_empty_string_clears_a_detail(profiled: TestClient) -> None:
    profiled.patch(
        "/api/v1/me",
        headers=HEADERS,
        json={"username": "alice", "gender": "male", "birthday": "1990-06-01"},
    )

    # The app serialises with explicitNulls=false, so null never reaches the
    # wire. Empty string is the only way it can take a value back.
    body = profiled.patch(
        "/api/v1/me",
        headers=HEADERS,
        json={"username": "alice", "gender": "", "birthday": ""},
    ).json()

    assert body["gender"] is None
    assert body["birthday"] is None


@pytest.mark.parametrize("gender", ["male ", " FEMALE", "Other"])
def test_gender_accepts_surrounding_space_and_case(profiled: TestClient, gender: str) -> None:
    response = profiled.patch(
        "/api/v1/me",
        headers=HEADERS,
        json={"username": "alice", "gender": gender},
    )

    assert response.status_code == 200
    assert response.json()["gender"] == gender.strip().lower()


@pytest.mark.parametrize("gender", ["man", "f", "nonbinary", "1"])
def test_unknown_genders_are_rejected(profiled: TestClient, gender: str) -> None:
    response = profiled.patch(
        "/api/v1/me",
        headers=HEADERS,
        json={"username": "alice", "gender": gender},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "birthday",
    ["17-04-1998", "1998/04/17", "not a date", "1998-13-01", "1998-02-30", "3000-01-01"],
)
def test_invalid_birthdays_are_rejected(profiled: TestClient, birthday: str) -> None:
    response = profiled.patch(
        "/api/v1/me",
        headers=HEADERS,
        json={"username": "alice", "birthday": birthday},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_details_are_the_callers_own(profiled: TestClient) -> None:
    profiled.patch(
        "/api/v1/me",
        headers=HEADERS,
        json={"username": "alice", "gender": "female", "birthday": "1998-04-17"},
    )

    body = profiled.get("/api/v1/me", headers=OTHER).json()

    assert body["gender"] is None
    assert body["birthday"] is None
