from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import USER_A, USER_B

BearerFactory = Callable[..., dict[str, str]]
TokenFactory = Callable[..., str]


def create_project(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"prompt": "A paper lantern drifting over water", "provider": "fake"},
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- identity ---------------------------------------------------------------


def test_valid_token_resolves_the_subject_as_canonical_identity(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    created = create_project(supabase_client, bearer(subject=USER_A))

    # A second, differently-signed token for the same subject must see the same
    # data: identity is the `sub` claim, not the token string.
    listed = supabase_client.get(
        "/api/v1/projects",
        headers=bearer(subject=USER_A, expires_in=7200, email="a@example.com"),
    )

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [created["id"]]


def test_audience_may_be_a_list(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    response = supabase_client.get(
        "/api/v1/projects",
        headers=bearer(audience=["authenticated", "other"]),
    )

    assert response.status_code == 200


def test_health_stays_public(supabase_client: TestClient) -> None:
    assert supabase_client.get("/api/v1/health").status_code == 200


# --- missing or malformed credentials ---------------------------------------


def test_missing_token_is_unauthenticated(supabase_client: TestClient) -> None:
    response = supabase_client.get("/api/v1/projects")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize(
    "header",
    ["", "token abc", "Bearer", "Bearer    ", "Basic dXNlcjpwYXNz"],
)
def test_malformed_authorization_header_is_unauthenticated(
    supabase_client: TestClient,
    header: str,
) -> None:
    response = supabase_client.get("/api/v1/projects", headers={"Authorization": header})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_bearer_scheme_is_case_insensitive(
    supabase_client: TestClient,
    make_token: TokenFactory,
) -> None:
    response = supabase_client.get(
        "/api/v1/projects",
        headers={"Authorization": f"bearer {make_token()}"},
    )

    assert response.status_code == 200


# --- rejected tokens --------------------------------------------------------


def _assert_token_invalid(response: Any) -> None:
    assert response.status_code == 401, response.text
    body = response.json()
    assert body["error"]["code"] == "TOKEN_INVALID"
    # The envelope must not reveal which check failed.
    assert body["error"]["message"] == "Your session has expired. Please sign in again."


def test_expired_token_is_rejected(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    _assert_token_invalid(supabase_client.get("/api/v1/projects", headers=bearer(expires_in=-60)))


def test_wrong_signature_is_rejected(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    _assert_token_invalid(
        supabase_client.get(
            "/api/v1/projects",
            headers=bearer(secret="an-attacker-supplied-signing-key"),
        )
    )


def test_wrong_issuer_is_rejected(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    _assert_token_invalid(
        supabase_client.get(
            "/api/v1/projects",
            headers=bearer(issuer="https://evil.example.com/auth/v1"),
        )
    )


def test_wrong_audience_is_rejected(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    _assert_token_invalid(supabase_client.get("/api/v1/projects", headers=bearer(audience="anon")))


def test_unsigned_alg_none_token_is_rejected(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    _assert_token_invalid(
        supabase_client.get(
            "/api/v1/projects",
            headers=bearer(algorithm="none", signature=""),
        )
    )


def test_algorithm_substitution_is_rejected(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    # Correctly signed, but not with the algorithm this server pins.
    _assert_token_invalid(
        supabase_client.get("/api/v1/projects", headers=bearer(algorithm="HS512"))
    )


def test_token_without_subject_is_rejected(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    _assert_token_invalid(
        supabase_client.get("/api/v1/projects", headers=bearer(include_subject=False))
    )


def test_malformed_token_is_rejected(
    supabase_client: TestClient,
) -> None:
    _assert_token_invalid(
        supabase_client.get(
            "/api/v1/projects",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
    )


def test_tampered_subject_is_rejected(
    supabase_client: TestClient,
    make_token: TokenFactory,
) -> None:
    header_segment, payload_segment, signature_segment = make_token(subject=USER_A).split(".")
    padding = "=" * (-len(payload_segment) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload_segment + padding))
    claims["sub"] = USER_B
    forged = (
        base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )

    _assert_token_invalid(
        supabase_client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {header_segment}.{forged}.{signature_segment}"},
        )
    )


# --- development identity is confined to the dev profile --------------------


def test_debug_header_alone_cannot_authenticate(supabase_client: TestClient) -> None:
    response = supabase_client.get("/api/v1/projects", headers={"X-Debug-User-Id": USER_B})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_debug_header_cannot_override_a_verified_identity(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    created = create_project(supabase_client, bearer(subject=USER_A))

    stolen = supabase_client.get(
        f"/api/v1/projects/{created['id']}",
        headers={**bearer(subject=USER_B), "X-Debug-User-Id": USER_A},
    )

    assert stolen.status_code == 404


# --- owner isolation --------------------------------------------------------


def test_another_user_cannot_read_update_or_delete_a_project(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    created = create_project(supabase_client, bearer(subject=USER_A))
    intruder = bearer(subject=USER_B)

    assert (
        supabase_client.get(f"/api/v1/projects/{created['id']}", headers=intruder).status_code
        == 404
    )
    assert (
        supabase_client.post(
            f"/api/v1/projects/{created['id']}/retry", headers=intruder
        ).status_code
        == 404
    )
    assert (
        supabase_client.delete(f"/api/v1/projects/{created['id']}", headers=intruder).status_code
        == 404
    )
    assert supabase_client.get("/api/v1/projects", headers=intruder).json()["items"] == []

    # The owner's project survived every attempt.
    owner_view = supabase_client.get(f"/api/v1/projects/{created['id']}", headers=bearer())
    assert owner_view.status_code == 200


# --- email write-through ------------------------------------------------------


def test_the_tokens_email_is_written_through_to_the_profile(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    # The signup trigger seeded a@example.com and never revisited the row, so
    # a later address change only exists in the token until this syncs it.
    response = supabase_client.get(
        "/api/v1/me",
        headers=bearer(subject=USER_A, email="alice.new@example.com"),
    )

    assert response.status_code == 200
    assert response.json()["email"] == "alice.new@example.com"

    stored = supabase_client.app.state.database.get_user(USER_A)
    assert stored["email"] == "alice.new@example.com"


def test_a_token_without_an_email_leaves_the_stored_one_alone(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    supabase_client.get("/api/v1/me", headers=bearer(subject=USER_A))

    stored = supabase_client.app.state.database.get_user(USER_A)
    assert stored["email"] == "a@example.com"


def test_the_write_through_only_touches_the_calling_account(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    supabase_client.get(
        "/api/v1/me",
        headers=bearer(subject=USER_A, email="changed@example.com"),
    )

    database = supabase_client.app.state.database
    assert database.get_user(USER_B)["email"] == "b@example.com"


def test_the_email_claim_cannot_grant_a_role(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    # Email is the one claim now trusted enough to persist. Authority still
    # comes from the row (SECURITY.md 2), so it must not travel with it.
    supabase_client.get(
        "/api/v1/me",
        headers=bearer(subject=USER_A, email="admin@cretona.test"),
    )

    body = supabase_client.get(
        "/api/v1/me",
        headers=bearer(subject=USER_A, email="admin@cretona.test"),
    ).json()

    assert body["role"] == "user"
    assert supabase_client.get(
        "/api/v1/admin/users",
        headers=bearer(subject=USER_A, email="admin@cretona.test"),
    ).status_code == 403


# --- first sign-in provisioning ----------------------------------------------

NEW_ACCOUNT = "3f8d9c22-5b41-4f7e-9a03-77c2d1e4b8a6"


def test_a_new_account_is_provisioned_on_its_first_request(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    # The local sqlite mirror has no Supabase signup trigger, so an account
    # created through the app has no row here until this makes one.
    assert supabase_client.app.state.database.get_user(NEW_ACCOUNT) is None

    response = supabase_client.get(
        "/api/v1/me",
        headers=bearer(subject=NEW_ACCOUNT, email="brand.new@example.com"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == NEW_ACCOUNT
    assert body["email"] == "brand.new@example.com"


def test_a_provisioned_account_starts_with_nothing_chosen(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    body = supabase_client.get(
        "/api/v1/me",
        headers=bearer(subject=NEW_ACCOUNT, email="brand.new@example.com"),
    ).json()

    # No username is what sends a fresh account into profile setup; the
    # optional details read as unanswered rather than as someone else's.
    assert body["username"] is None
    assert body["gender"] is None
    assert body["birthday"] is None


def test_provisioning_never_grants_a_role(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    # An address that looks privileged is still just an address.
    headers = bearer(subject=NEW_ACCOUNT, email="admin@cretona.test")

    body = supabase_client.get("/api/v1/me", headers=headers).json()

    # Authority comes from the row, never from a claim the client influences.
    assert body["role"] == "user"
    assert supabase_client.get("/api/v1/admin/users", headers=headers).status_code == 403


def test_provisioning_happens_once(
    supabase_client: TestClient,
    bearer: BearerFactory,
) -> None:
    headers = bearer(subject=NEW_ACCOUNT, email="brand.new@example.com")
    supabase_client.get("/api/v1/me", headers=headers)
    supabase_client.patch("/api/v1/me", headers=headers, json={"username": "brandnew"})

    # A second request must not reset the profile the account just completed.
    body = supabase_client.get("/api/v1/me", headers=headers).json()
    assert body["username"] == "brandnew"
