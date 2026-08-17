"""Parity tests for the Supabase/Postgres adapter.

Skipped unless CRETONA_TEST_DATABASE_URL points at a disposable Postgres. They
assert that the behaviours the API contract promises hold on Postgres exactly
as they do on SQLite, because a repository swap that quietly changed ownership
or pagination would be invisible to the SQLite suite.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app.postgres import SELECTED_COLUMNS, PostgresDatabase
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


def test_rate_limit_is_atomic_across_postgres_instances(
    postgres_client: TestClient,
    postgres_url: str,
) -> None:
    first = PostgresDatabase(postgres_url, min_size=1, max_size=4)
    second = PostgresDatabase(postgres_url, min_size=1, max_size=4)
    first.initialize()
    second.initialize()

    try:
        stores = [first, second] * 10
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda store: store.consume_rate_limit(
                        "shared-caller",
                        "default",
                        5,
                        60.0,
                    ),
                    stores,
                )
            )
    finally:
        first.close()
        second.close()

    assert sum(allowed for allowed, _remaining in results) == 5
    assert sorted(remaining for allowed, remaining in results if allowed) == [0, 1, 2, 3, 4]


# --- T3-3: consume_rate_limit collapsed from ~5-6 round trips to 2 -----------
#
# Measured against a live pooler at ~190ms/round trip, the original sequential
# implementation (lock, clock, caller-scoped delete, count, insert, then an
# unconditional global sweep) cost roughly a second per rate-limit check. These
# tests pin the sliding-window semantics and the sweep's sampling directly, so
# a future change to the SQL cannot silently widen the window or stop
# reclaiming abandoned callers' rows while still passing the atomicity test
# above (which only proves the limit cannot be exceeded, not that it stays
# accurate once rows start expiring).


def test_rate_limit_sliding_window_semantics_on_postgres(
    postgres_client: TestClient,
    postgres_url: str,
) -> None:
    """Exact boundary behaviour of the collapsed statement: N allowed, then
    refused, with `remaining` counting down and expired hits excluded.
    """
    store = PostgresDatabase(postgres_url, min_size=1, max_size=2)
    store.initialize()
    try:
        results = [store.consume_rate_limit("solo-caller", "default", 3, 60.0) for _ in range(4)]
    finally:
        store.close()

    assert results == [(True, 2), (True, 1), (True, 0), (False, 0)]


def test_expired_hits_do_not_count_against_the_window(
    postgres_client: TestClient,
    postgres_url: str,
) -> None:
    """A hit older than the window is pruned by the caller's own next call,
    not just by the sampled global sweep -- this is what keeps a caller who
    makes one request per window from ever being refused.
    """
    store = PostgresDatabase(postgres_url, min_size=1, max_size=2)
    store.initialize()
    try:
        with psycopg.connect(postgres_url, autocommit=True) as connection:
            connection.execute(
                "INSERT INTO public.rate_limit_hits (caller_key, bucket, occurred_at) "
                "VALUES ('stale-caller', 'default', clock_timestamp() - interval '2 minutes')"
            )
        allowed, remaining = store.consume_rate_limit("stale-caller", "default", 1, 60.0)
    finally:
        store.close()

    assert (allowed, remaining) == (True, 0)


def test_sweep_reclaims_another_callers_expired_rows_when_sampled(
    postgres_client: TestClient,
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sweep is sampled, not tied to any one caller's own prune -- this is
    what still bounds the table for a caller who never calls again.
    """
    store = PostgresDatabase(postgres_url, min_size=1, max_size=2)
    store.initialize()
    try:
        with psycopg.connect(postgres_url, autocommit=True) as connection:
            connection.execute(
                "INSERT INTO public.rate_limit_hits (caller_key, bucket, occurred_at) "
                "VALUES ('abandoned-caller', 'default', clock_timestamp() - interval '2 minutes')"
            )
        monkeypatch.setattr("random.random", lambda: 0.0)  # forces the sample
        store.consume_rate_limit("someone-else", "default", 5, 60.0)

        with psycopg.connect(postgres_url, autocommit=True, row_factory=dict_row) as connection:
            remaining = connection.execute(
                "SELECT count(*) AS n FROM public.rate_limit_hits WHERE caller_key = %s",
                ("abandoned-caller",),
            ).fetchone()["n"]
    finally:
        store.close()

    assert remaining == 0


def test_sweep_does_not_run_on_every_call(
    postgres_client: TestClient,
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other side of sampling: most calls must NOT pay the sweep's round
    trip, or nothing was gained over the unconditional version.
    """
    store = PostgresDatabase(postgres_url, min_size=1, max_size=2)
    store.initialize()
    try:
        with psycopg.connect(postgres_url, autocommit=True) as connection:
            connection.execute(
                "INSERT INTO public.rate_limit_hits (caller_key, bucket, occurred_at) "
                "VALUES ('still-abandoned', 'default', clock_timestamp() - interval '2 minutes')"
            )
        monkeypatch.setattr("random.random", lambda: 0.99)  # forces skipping the sample
        store.consume_rate_limit("someone-else-again", "default", 5, 60.0)

        with psycopg.connect(postgres_url, autocommit=True, row_factory=dict_row) as connection:
            remaining = connection.execute(
                "SELECT count(*) AS n FROM public.rate_limit_hits WHERE caller_key = %s",
                ("still-abandoned",),
            ).fetchone()["n"]
    finally:
        store.close()

    assert remaining == 1


def test_consume_rate_limit_issues_two_round_trips_in_the_common_case(
    postgres_client: TestClient,
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pins the round-trip count directly, so the T3-3 rewrite's actual point
    -- fewer trips, not just equivalent behaviour -- cannot silently regress.
    """
    store = PostgresDatabase(postgres_url, min_size=1, max_size=2)
    store.initialize()
    try:
        monkeypatch.setattr("random.random", lambda: 0.99)  # exclude the sampled sweep trip

        calls = 0
        original = psycopg.Connection.execute

        def counting_execute(self: psycopg.Connection[Any], *args: Any, **kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            return original(self, *args, **kwargs)

        monkeypatch.setattr(psycopg.Connection, "execute", counting_execute)
        store.consume_rate_limit("counted-caller", "default", 5, 60.0)
    finally:
        store.close()

    assert calls == 2


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

    assert (
        postgres_client.get(f"/api/v1/projects/{created['id']}", headers=intruder).status_code
        == 404
    )
    assert (
        postgres_client.delete(f"/api/v1/projects/{created['id']}", headers=intruder).status_code
        == 404
    )
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

    assert (
        postgres_client.delete(f"/api/v1/projects/{created['id']}", headers=headers).status_code
        == 204
    )
    assert (
        postgres_client.get(f"/api/v1/projects/{created['id']}", headers=headers).status_code == 404
    )
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


def test_generation_log_retention_is_atomic_on_postgres(
    postgres_client: TestClient,
    bearer: BearerFactory,
    postgres_url: str,
) -> None:
    created = create_project(postgres_client, bearer(subject=USER_A))
    with psycopg.connect(postgres_url) as connection:
        connection.execute(
            "UPDATE public.generation_logs SET created_at = '2000-01-01T00:00:00Z' "
            "WHERE project_id = %s",
            (created["id"],),
        )

    # A current row proves the cutoff is selective rather than a table wipe.
    postgres_client.app.state.generation_log.record(
        project_id=created["id"], provider="fake", event="poll", http_status=200
    )

    summary = postgres_client.app.state.generation_log.prune(
        retention_days=180,
        batch_size=10,
        now=datetime(2026, 8, 12, 12, tzinfo=UTC),
    )

    assert summary.deleted == 1
    assert [
        row["event"] for row in postgres_client.app.state.database.generation_logs(created["id"])
    ] == ["poll"]


def test_postgres_schema_has_the_retention_index(
    postgres_client: TestClient,
    postgres_url: str,
) -> None:
    with psycopg.connect(postgres_url) as connection:
        row = connection.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
            "AND indexname = 'idx_logs_retention'"
        ).fetchone()

    assert row is not None
    assert "created_at" in row[0]


def test_audit_rows_round_trip_through_jsonb(
    postgres_client: TestClient,
    postgres_url: str,
) -> None:
    """The audit path had no Postgres test at all.

    It was written with json.dumps against a jsonb column, so `details` was
    either rejected or stored as a JSON string. Only Postgres shows that;
    SQLite stores text either way.
    """
    database = postgres_client.app.state.database
    database.insert_audit_log(
        id="11111111-2222-4333-8444-555555555555",
        actor_id=USER_B,
        action="user_updated",
        target_type="user",
        target_id=USER_A,
        details={"roleFrom": "user", "roleTo": "admin"},
        created_at="2026-08-15T00:00:00Z",
    )

    rows = database.list_audit_logs(limit=10, cursor=None, action=None, actor_id=None)[0]

    assert len(rows) == 1
    # An object, not a string: the read path returns usable structure.
    assert rows[0]["details"] == {"roleFrom": "user", "roleTo": "admin"}


def test_a_system_wide_audit_row_needs_no_target(
    postgres_client: TestClient,
) -> None:
    """Migration 008 originally made target_id NOT NULL.

    The thumbnail backfill audits a system-wide action with no single target,
    so that constraint would have failed every backfill after it had already
    done the work.
    """
    database = postgres_client.app.state.database

    database.insert_audit_log(
        id="99999999-2222-4333-8444-555555555555",
        actor_id=USER_B,
        action="thumbnails_backfilled",
        target_type="system",
        details={"backfilled": 0, "processed": 0},
        created_at="2026-08-15T00:00:00Z",
    )

    rows = database.list_audit_logs(limit=10, cursor=None, action=None, actor_id=None)[0]
    assert rows[0]["target_id"] is None


def test_an_audit_row_survives_the_actor(
    postgres_client: TestClient,
    postgres_url: str,
) -> None:
    """No cascade from users: the trail must outlive the account."""
    database = postgres_client.app.state.database
    database.insert_audit_log(
        id="77777777-2222-4333-8444-555555555555",
        actor_id=USER_B,
        action="user_updated",
        target_type="user",
        target_id=USER_A,
        details={},
        created_at="2026-08-15T00:00:00Z",
    )

    with psycopg.connect(postgres_url, autocommit=True, connect_timeout=5) as connection:
        connection.execute("DELETE FROM public.users WHERE id = %s", (USER_B,))

    rows = database.list_audit_logs(limit=10, cursor=None, action=None, actor_id=None)[0]
    assert len(rows) == 1


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

    response = postgres_client.post(f"/api/v1/projects/{created['id']}/retry", headers=headers)

    assert response.status_code == expected
