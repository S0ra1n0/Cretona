"""Parity tests for the Supabase/Postgres adapter.

Skipped unless CRETONA_TEST_DATABASE_URL points at a disposable Postgres. They
assert that the behaviours the API contract promises hold on Postgres exactly
as they do on SQLite, because a repository swap that quietly changed ownership
or pagination would be invisible to the SQLite suite.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.postgres import SELECTED_COLUMNS
from tests.conftest import USER_A, USER_B

BearerFactory = Callable[..., dict[str, str]]


def create_project(
    client: TestClient,
    headers: dict[str, str],
    *,
    prompt: str = "A paper boat crossing a neon river",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    request_headers = dict(headers)
    if idempotency_key:
        request_headers["Idempotency-Key"] = idempotency_key
    response = client.post(
        "/api/v1/projects",
        headers=request_headers,
        json={
            "prompt": prompt,
            "provider": "fake",
            "options": {"durationSeconds": 5, "aspectRatio": "9:16"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_every_selected_column_exists(postgres_client: TestClient, postgres_url: str) -> None:
    """Guards the adapter against schema drift in postgres_schema.sql."""
    expected = {column.strip() for column in SELECTED_COLUMNS.split(",")}

    with psycopg.connect(postgres_url) as connection:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'video_projects'"
        ).fetchall()

    assert expected <= {row[0] for row in rows}


def test_lifecycle_reaches_a_playable_video(
    postgres_client: TestClient,
    bearer: BearerFactory,
) -> None:
    headers = bearer(subject=USER_A)
    created = create_project(postgres_client, headers)
    assert created["status"] == "pending"
    assert created["aspectRatio"] == "9:16"

    generating = postgres_client.get(f"/api/v1/projects/{created['id']}", headers=headers)
    assert generating.json()["status"] == "generating"

    completed = postgres_client.get(f"/api/v1/projects/{created['id']}", headers=headers)
    body = completed.json()
    assert body["status"] == "completed"
    # Re-hosted under an owner-scoped key, not left as the provider's path.
    assert body["videoUrl"].endswith(f"/media/{USER_A}/{created['id']}/video.mp4")
    assert body["completedAt"]
    # The ratio survived the round trip, which is what migration 003 exists for.
    assert body["aspectRatio"] == "9:16"


def test_ownership_is_enforced_in_postgres(
    postgres_client: TestClient,
    bearer: BearerFactory,
) -> None:
    created = create_project(postgres_client, bearer(subject=USER_A))
    intruder = bearer(subject=USER_B)

    assert postgres_client.get(
        f"/api/v1/projects/{created['id']}", headers=intruder
    ).status_code == 404
    assert postgres_client.delete(
        f"/api/v1/projects/{created['id']}", headers=intruder
    ).status_code == 404
    assert postgres_client.get("/api/v1/projects", headers=intruder).json()["items"] == []


def test_idempotent_create_returns_the_original(
    postgres_client: TestClient,
    bearer: BearerFactory,
) -> None:
    headers = bearer(subject=USER_A)
    key = "6f1a1f4e-77b1-4a6c-9a3f-2b4a1c9d8e70"

    first = create_project(postgres_client, headers, idempotency_key=key)
    second = create_project(postgres_client, headers, idempotency_key=key)

    assert second["id"] == first["id"]
    assert len(postgres_client.get("/api/v1/projects", headers=headers).json()["items"]) == 1


def test_cursor_pagination_has_no_duplicates(
    postgres_client: TestClient,
    bearer: BearerFactory,
) -> None:
    headers = bearer(subject=USER_A)
    for index in range(3):
        create_project(postgres_client, headers, prompt=f"project {index}")

    first = postgres_client.get("/api/v1/projects?limit=2", headers=headers).json()
    assert len(first["items"]) == 2
    assert first["page"]["hasMore"] is True

    second = postgres_client.get(
        f"/api/v1/projects?limit=2&cursor={first['page']['nextCursor']}",
        headers=headers,
    ).json()

    assert len(second["items"]) == 1
    assert second["page"]["hasMore"] is False
    assert len({item["id"] for item in first["items"] + second["items"]}) == 3


def test_delete_is_soft_and_retains_the_row(
    postgres_client: TestClient,
    bearer: BearerFactory,
    postgres_url: str,
) -> None:
    headers = bearer(subject=USER_A)
    created = create_project(postgres_client, headers)

    assert postgres_client.delete(
        f"/api/v1/projects/{created['id']}", headers=headers
    ).status_code == 204
    assert postgres_client.get(
        f"/api/v1/projects/{created['id']}", headers=headers
    ).status_code == 404
    assert postgres_client.get("/api/v1/projects", headers=headers).json()["items"] == []

    # A late provider callback needs a row to write to, so it is retained.
    with psycopg.connect(postgres_url) as connection:
        row = connection.execute(
            "SELECT deleted_at FROM public.video_projects WHERE id = %s",
            (created["id"],),
        ).fetchone()

    assert row is not None
    assert row[0] is not None


def test_generating_project_cannot_be_deleted(
    postgres_client: TestClient,
    bearer: BearerFactory,
) -> None:
    headers = bearer(subject=USER_A)
    created = create_project(postgres_client, headers)
    postgres_client.get(f"/api/v1/projects/{created['id']}", headers=headers)

    response = postgres_client.delete(f"/api/v1/projects/{created['id']}", headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_malformed_project_id_is_not_found_rather_than_a_server_error(
    postgres_client: TestClient,
    bearer: BearerFactory,
) -> None:
    response = postgres_client.get("/api/v1/projects/not-a-uuid", headers=bearer(subject=USER_A))

    assert response.status_code == 404


def test_disabled_account_is_refused(
    postgres_client: TestClient,
    bearer: BearerFactory,
    postgres_url: str,
) -> None:
    with psycopg.connect(postgres_url, autocommit=True) as connection:
        connection.execute(
            "UPDATE public.users SET is_disabled = true WHERE id = %s",
            (USER_B,),
        )

    response = postgres_client.get("/api/v1/projects", headers=bearer(subject=USER_B))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCOUNT_DISABLED"


def test_token_without_a_profile_row_is_refused(
    postgres_client: TestClient,
    bearer: BearerFactory,
) -> None:
    # Verifies, but the signup trigger never created a profile.
    orphan = bearer(subject="99999999-0000-4000-8000-000000000009")

    response = postgres_client.get("/api/v1/projects", headers=orphan)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_INVALID"


def test_poller_claims_in_flight_work_on_postgres(
    postgres_client: TestClient,
    bearer: BearerFactory,
) -> None:
    headers = bearer(subject=USER_A)
    created = create_project(postgres_client, headers)

    # FOR UPDATE SKIP LOCKED is Postgres-only syntax, so this is the only
    # place the poller's claim query actually runs.
    poller = postgres_client.app.state.poller
    assert poller.run_once() == 1
    assert poller.run_once() == 1

    row = postgres_client.app.state.database.get_project(created["id"], USER_A)
    assert row["status"] == "completed"

    # Nothing in flight left to claim.
    assert poller.run_once() == 0


def test_generation_logs_are_written_to_jsonb(
    postgres_client: TestClient,
    bearer: BearerFactory,
) -> None:
    headers = bearer(subject=USER_A)
    created = create_project(postgres_client, headers)
    postgres_client.get(f"/api/v1/projects/{created['id']}", headers=headers)
    postgres_client.get(f"/api/v1/projects/{created['id']}", headers=headers)

    rows = postgres_client.app.state.database.generation_logs(created["id"])

    # The service swallows write failures by design, so this asserts the rows
    # actually landed rather than trusting the absence of an exception.
    assert [row["event"] for row in rows] == ["submit", "poll", "download"]
    # jsonb round-trips as a dict, not a string.
    assert rows[0]["request"]["prompt"] == "A paper boat crossing a neon river"
    assert rows[-1]["response"]["storedPath"].endswith("video.mp4")


def make_admin(postgres_url: str, user_id: str) -> None:
    with psycopg.connect(postgres_url, autocommit=True) as connection:
        connection.execute(
            "UPDATE public.users SET role_id = (SELECT id FROM public.roles "
            "WHERE name = 'admin') WHERE id = %s",
            (user_id,),
        )


def test_admin_listing_works_on_postgres(
    postgres_client: TestClient,
    bearer: BearerFactory,
    postgres_url: str,
) -> None:
    create_project(postgres_client, bearer(subject=USER_A))
    make_admin(postgres_url, USER_B)
    admin = bearer(subject=USER_B)

    body = postgres_client.get("/api/v1/admin/users", headers=admin).json()
    by_id = {item["id"]: item for item in body["items"]}

    assert set(by_id) == {USER_A, USER_B}
    assert by_id[USER_A]["projectCount"] == 1
    assert by_id[USER_B]["role"] == "admin"

    # ILIKE search and the role filter are Postgres-specific SQL.
    found = postgres_client.get("/api/v1/admin/users?q=A@EXAMPLE", headers=admin).json()
    assert [item["id"] for item in found["items"]] == [USER_A]

    admins = postgres_client.get("/api/v1/admin/users?role=admin", headers=admin).json()
    assert [item["id"] for item in admins["items"]] == [USER_B]


def test_admin_stats_work_on_postgres(
    postgres_client: TestClient,
    bearer: BearerFactory,
    postgres_url: str,
) -> None:
    created = create_project(postgres_client, bearer(subject=USER_A))
    postgres_client.get(f"/api/v1/projects/{created['id']}", headers=bearer(subject=USER_A))
    postgres_client.get(f"/api/v1/projects/{created['id']}", headers=bearer(subject=USER_A))
    make_admin(postgres_url, USER_B)

    body = postgres_client.get("/api/v1/admin/stats", headers=bearer(subject=USER_B)).json()

    assert body["totals"]["users"] == 2
    assert body["totals"]["projects"] == 1
    assert body["projectsByStatus"]["completed"] == 1
    assert body["projectsByProvider"]["fake"] == 1
    # date_trunc + FILTER are Postgres-specific.
    assert len(body["daily"]) == 1
    assert body["daily"][0]["completed"] == 1


def test_role_change_resolves_the_role_table_on_postgres(
    postgres_client: TestClient,
    bearer: BearerFactory,
    postgres_url: str,
) -> None:
    make_admin(postgres_url, USER_B)

    promoted = postgres_client.patch(
        f"/api/v1/admin/users/{USER_A}",
        headers=bearer(subject=USER_B),
        json={"role": "admin"},
    )

    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [("fail:provider_error upstream down", 202), ("fail:content_policy unsafe", 409)],
)
def test_retry_rules_match_the_reference(
    postgres_client: TestClient,
    bearer: BearerFactory,
    prompt: str,
    expected: int,
) -> None:
    headers = bearer(subject=USER_A)
    created = create_project(postgres_client, headers, prompt=prompt)
    postgres_client.get(f"/api/v1/projects/{created['id']}", headers=headers)
    postgres_client.get(f"/api/v1/projects/{created['id']}", headers=headers)

    response = postgres_client.post(
        f"/api/v1/projects/{created['id']}/retry", headers=headers
    )

    assert response.status_code == expected
