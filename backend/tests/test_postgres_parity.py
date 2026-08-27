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
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app.errors import AppError
from app.postgres import SELECTED_COLUMNS, PostgresDatabase, SchemaMismatchError
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


def test_profile_details_round_trip_on_postgres(
    postgres_client: TestClient,
    bearer: BearerFactory,
) -> None:
    headers = bearer()

    updated = postgres_client.patch(
        "/api/v1/me",
        headers=headers,
        json={"username": "alice", "gender": "female", "birthday": "1998-04-17"},
    )
    fetched = postgres_client.get("/api/v1/me", headers=headers)

    assert updated.status_code == 200, updated.text
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["gender"] == "female"
    assert fetched.json()["birthday"] == "1998-04-17"


def test_startup_rejects_schema_missing_profile_details(postgres_url: str) -> None:
    schema = (Path(__file__).parent / "postgres_schema.sql").read_text(encoding="utf-8")
    with psycopg.connect(postgres_url, autocommit=True) as connection:
        connection.execute(schema)
        connection.execute("ALTER TABLE public.users DROP COLUMN gender, DROP COLUMN birthday")

    store = PostgresDatabase(postgres_url, min_size=1, max_size=2)
    try:
        with pytest.raises(SchemaMismatchError, match="012_add_user_profile_fields"):
            store.initialize()
    finally:
        store.close()


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


# --- credits (S-04/S-05) -----------------------------------------------------
#
# The whole point of this section: every credit method has a second
# implementation in app/postgres.py that the sqlite suite never touches.
# `%s` placeholders, `FILTER (WHERE ...)`, `::timestamptz` casts and the
# uuid -> str normalisation in `_to_credit_row` are all Postgres-only code, and
# a mistake in any of them would only ever surface in production.


def credit_service(client: TestClient):
    return client.app.state.credit_service


def test_credits_grant_and_charge_on_postgres(postgres_client: TestClient) -> None:
    credits = credit_service(postgres_client)
    start = credits.balance(USER_A)

    row, created = credits.charge(USER_A, 3, ref_type="project", ref_id="p1")

    assert created is True
    assert row["delta"] == -3
    assert row["balance_after"] == start - 3
    assert credits.balance(USER_A) == start - 3
    # uuid columns must arrive as strings, or the service layer would be
    # holding a different type on each backend.
    assert isinstance(row["id"], str)
    assert isinstance(row["user_id"], str)
    assert isinstance(row["created_at"], str)
    assert row["created_at"].endswith("Z")


def test_a_charge_beyond_the_balance_is_refused_on_postgres(
    postgres_client: TestClient,
) -> None:
    credits = credit_service(postgres_client)
    balance = credits.balance(USER_A)

    with pytest.raises(AppError) as excinfo:
        credits.charge(USER_A, balance + 1, ref_type="project", ref_id="p1")

    assert excinfo.value.status_code == 402
    assert credits.balance(USER_A) == balance


def test_the_non_negative_constraint_is_live_on_postgres(
    postgres_client: TestClient, postgres_url: str
) -> None:
    """The guard is a CHECK, not a Python branch. Prove it bites."""
    with psycopg.connect(postgres_url, autocommit=True) as connection:  # noqa: SIM117
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                "UPDATE public.users SET credit_balance = -1 WHERE id = %s", (USER_A,)
            )


def test_a_replayed_key_charges_once_on_postgres(postgres_client: TestClient) -> None:
    credits = credit_service(postgres_client)
    start = credits.balance(USER_A)

    first, created_first = credits.charge(USER_A, 1, idempotency_key="PG-KEY")
    second, created_second = credits.charge(USER_A, 1, idempotency_key="PG-KEY")

    assert created_first is True
    assert created_second is False
    assert first["id"] == second["id"]
    assert credits.balance(USER_A) == start - 1


def test_refund_reads_back_the_original_amount_on_postgres(
    postgres_client: TestClient,
) -> None:
    credits = credit_service(postgres_client)
    start = credits.balance(USER_A)
    credits.charge(USER_A, 4, ref_type="project", ref_id="pg-refund")

    refund = credits.refund_for(USER_A, ref_type="project", ref_id="pg-refund")

    assert refund is not None
    assert refund["delta"] == 4
    assert credits.balance(USER_A) == start
    assert credits.refund_for(USER_A, ref_type="project", ref_id="pg-refund") is None


def test_totals_and_history_on_postgres(postgres_client: TestClient) -> None:
    credits = credit_service(postgres_client)
    credits.grant(USER_A, 7, reason="event_grant")
    credits.charge(USER_A, 2, ref_type="project", ref_id="pg-hist")

    granted, spent = credits.totals(USER_A)
    assert granted >= 7
    assert spent >= 2

    rows, cursor = credits.history(USER_A, limit=1)
    assert len(rows) == 1
    assert cursor is not None

    page_two, _ = credits.history(USER_A, limit=1, cursor=cursor)
    assert page_two
    assert rows[0]["id"] != page_two[0]["id"]

    only_grants, _ = credits.history(USER_A, reason="event_grant")
    assert all(row["reason"] == "event_grant" for row in only_grants)


def test_the_ledger_explains_the_balance_on_postgres(postgres_client: TestClient) -> None:
    credits = credit_service(postgres_client)
    credits.charge(USER_A, 2, ref_type="project", ref_id="pg-drift")
    credits.refund_for(USER_A, ref_type="project", ref_id="pg-drift")
    credits.grant(USER_B, 5, reason="purchase")

    assert postgres_client.app.state.database.ledger_drift() == []


def test_drift_is_detectable_on_postgres(
    postgres_client: TestClient, postgres_url: str
) -> None:
    """Going around CreditService is exactly what the check has to catch."""
    with psycopg.connect(postgres_url, autocommit=True) as connection:
        connection.execute(
            "UPDATE public.users SET credit_balance = credit_balance + 999 WHERE id = %s",
            (USER_B,),
        )

    assert postgres_client.app.state.database.ledger_drift() == [USER_B]


def test_concurrent_charges_cannot_overspend_on_postgres(
    postgres_client: TestClient,
) -> None:
    """The one that matters, on the backend production actually runs.

    Ten threads race a balance that covers three. The guard is the UPDATE's
    WHERE clause, so exactly three may win no matter how they interleave.
    """
    credits = credit_service(postgres_client)
    # Spend down to a known, small balance first.
    credits.charge(USER_A, credits.balance(USER_A) - 3, ref_type="project", ref_id="pg-drain")
    assert credits.balance(USER_A) == 3

    def spend(index: int) -> bool:
        try:
            credits.charge(USER_A, 1, ref_type="project", ref_id=f"pg-race-{index}")
        except AppError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(spend, range(10)))

    assert sum(results) == 3
    assert credits.balance(USER_A) == 0
    assert postgres_client.app.state.database.ledger_drift() == []


def test_settings_round_trip_on_postgres(postgres_client: TestClient) -> None:
    database = postgres_client.app.state.database
    database.set_setting(
        "generation_cost_credits",
        "4",
        updated_by=USER_A,
        updated_at="2026-08-28T00:00:00Z",
    )

    assert database.get_setting("generation_cost_credits") == "4"
    assert credit_service(postgres_client).generation_cost() == 4
    assert database.get_setting("no_such_key") is None


def test_the_auto_grant_event_is_found_on_postgres(
    postgres_client: TestClient, postgres_url: str
) -> None:
    """Drives `find_auto_grant_event`, including its timestamptz comparisons."""
    with psycopg.connect(postgres_url, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO public.events (code, name, kind, bonus_credits, recurrence, "
            " starts_at, ends_at, auto_grant, is_active) VALUES "
            "('PG_SIGNUP', 'Welcome', 'grant', 5, 'once', "
            " now() - interval '1 day', now() + interval '1 day', true, true)"
        )

    event = postgres_client.app.state.database.find_auto_grant_event(
        datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )

    assert event is not None
    assert event["code"] == "PG_SIGNUP"
    assert event["bonus_credits"] == 5
    assert isinstance(event["id"], str)


def test_an_expired_auto_grant_event_is_not_found_on_postgres(
    postgres_client: TestClient, postgres_url: str
) -> None:
    with psycopg.connect(postgres_url, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO public.events (code, name, kind, bonus_credits, recurrence, "
            " starts_at, ends_at, auto_grant, is_active) VALUES "
            "('PG_EXPIRED', 'Old', 'grant', 5, 'once', "
            " now() - interval '10 day', now() - interval '1 day', true, true)"
        )

    event = postgres_client.app.state.database.find_auto_grant_event(
        datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )

    assert event is None or event["code"] != "PG_EXPIRED"


def test_the_signup_bonus_lands_through_the_api_on_postgres(
    postgres_client: TestClient, bearer: BearerFactory, postgres_url: str
) -> None:
    """End to end on Postgres: reading the profile grants the bonus once."""
    with psycopg.connect(postgres_url, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO public.events (code, name, kind, bonus_credits, recurrence, "
            " starts_at, ends_at, auto_grant, is_active) VALUES "
            "('PG_WELCOME', 'Welcome', 'grant', 5, 'once', "
            " now() - interval '1 day', now() + interval '1 day', true, true)"
        )

    credits = credit_service(postgres_client)
    before = credits.balance(USER_B)

    for _ in range(3):
        postgres_client.get("/api/v1/me", headers=bearer(subject=USER_B))

    assert credits.balance(USER_B) == before + 5


# --- packages and payments (S-07) --------------------------------------------
#
# `record_payment` writes the payment row, the ledger row and the balance in
# one transaction, and its Postgres implementation shares no code with the
# sqlite one. Untested, a mistake here would grant credits with no payment
# behind them, or take a payment that granted nothing.


def seed_package(postgres_url: str, name: str = "Starter") -> str:
    with psycopg.connect(postgres_url, autocommit=True, row_factory=dict_row) as connection:
        row = connection.execute(
            "INSERT INTO public.credit_packages (name, credits, price_vnd, sort_order) "
            "VALUES (%s, 10, 20000, 1) RETURNING id",
            (name,),
        ).fetchone()
    return str(row["id"])


def test_packages_list_and_fetch_on_postgres(
    postgres_client: TestClient, postgres_url: str
) -> None:
    package_id = seed_package(postgres_url, "PG Starter")
    database = postgres_client.app.state.database

    listed = database.list_credit_packages()
    fetched = database.get_credit_package(package_id)

    assert any(row["id"] == package_id for row in listed)
    assert fetched is not None
    # uuid must arrive as a string, or the service would hold a different type
    # per backend.
    assert isinstance(fetched["id"], str)
    assert fetched["is_active"] is True
    assert database.get_credit_package("not-a-uuid") is None


def test_a_purchase_is_atomic_on_postgres(
    postgres_client: TestClient, postgres_url: str
) -> None:
    package_id = seed_package(postgres_url, "PG Atomic")
    credits = postgres_client.app.state.credit_service
    payments = postgres_client.app.state.payment_service
    before = credits.balance(USER_A)

    payment = payments.purchase(USER_A, package_id, str(uuid4()))

    assert payment["status"] == "completed"
    assert payment["method"] == "simulated"
    assert credits.balance(USER_A) == before + 10
    assert payment["balance"] == before + 10
    assert isinstance(payment["id"], str)
    assert payment["created_at"].endswith("Z")

    rows, _ = credits.history(USER_A, limit=1)
    assert rows[0]["reason"] == "purchase"
    assert rows[0]["ref_id"] == payment["id"]
    assert postgres_client.app.state.database.ledger_drift() == []


def test_a_replayed_purchase_grants_once_on_postgres(
    postgres_client: TestClient, postgres_url: str
) -> None:
    package_id = seed_package(postgres_url, "PG Replay")
    credits = postgres_client.app.state.credit_service
    payments = postgres_client.app.state.payment_service
    before = credits.balance(USER_A)
    key = str(uuid4())

    first = payments.purchase(USER_A, package_id, key)
    second = payments.purchase(USER_A, package_id, key)

    assert first["id"] == second["id"]
    assert credits.balance(USER_A) == before + 10


def test_an_unknown_package_leaves_nothing_behind_on_postgres(
    postgres_client: TestClient, postgres_url: str
) -> None:
    credits = postgres_client.app.state.credit_service
    payments = postgres_client.app.state.payment_service
    before = credits.balance(USER_A)

    with pytest.raises(AppError) as excinfo:
        payments.purchase(USER_A, str(uuid4()), str(uuid4()))

    assert excinfo.value.status_code == 404
    assert credits.balance(USER_A) == before
    with psycopg.connect(postgres_url, row_factory=dict_row) as connection:
        count = connection.execute("SELECT COUNT(*) AS n FROM public.payments").fetchone()
    assert count["n"] == 0


# --- events (S-11) -----------------------------------------------------------
#
# `claim_event` on Postgres uses `INSERT ... SELECT ... WHERE ... ON CONFLICT
# DO NOTHING RETURNING *` to enforce the cap and the once-per-period rule in a
# single statement. That construct shares nothing with the sqlite version, and
# if it silently inserted nothing the caller would read it as "full" forever.


def seed_event(postgres_url: str, *, bonus: int = 10, max_claims: int | None = None) -> str:
    with psycopg.connect(postgres_url, autocommit=True, row_factory=dict_row) as connection:
        row = connection.execute(
            "INSERT INTO public.events (code, name, kind, bonus_credits, recurrence, "
            " starts_at, ends_at, max_claims, is_active) VALUES "
            "(%s, 'PG event', 'grant', %s, 'once', now() - interval '1 day', "
            " now() + interval '30 day', %s, true) RETURNING id",
            (f"PG_{uuid4().hex[:8]}", bonus, max_claims),
        ).fetchone()
    return str(row["id"])


def test_claiming_grants_credits_on_postgres(
    postgres_client: TestClient, postgres_url: str
) -> None:
    event_id = seed_event(postgres_url, bonus=12)
    events = postgres_client.app.state.event_service
    credits = postgres_client.app.state.credit_service
    before = credits.balance(USER_A)

    result = events.claim(USER_A, event_id)

    assert result["credits_granted"] == 12
    assert result["balance"] == before + 12
    assert isinstance(result["transaction_id"], str)

    rows, _ = credits.history(USER_A, limit=1)
    assert rows[0]["reason"] == "event_grant"
    assert rows[0]["ref_id"] == event_id
    assert postgres_client.app.state.database.ledger_drift() == []


def test_claiming_twice_is_refused_on_postgres(
    postgres_client: TestClient, postgres_url: str
) -> None:
    event_id = seed_event(postgres_url)
    events = postgres_client.app.state.event_service
    credits = postgres_client.app.state.credit_service
    events.claim(USER_A, event_id)
    after_first = credits.balance(USER_A)

    with pytest.raises(AppError) as excinfo:
        events.claim(USER_A, event_id)

    assert excinfo.value.code == "EVENT_ALREADY_CLAIMED"
    assert credits.balance(USER_A) == after_first


def test_a_full_event_is_refused_on_postgres(
    postgres_client: TestClient, postgres_url: str
) -> None:
    """The cap lives in the INSERT's WHERE clause. Prove it actually bites."""
    event_id = seed_event(postgres_url, max_claims=1)
    events = postgres_client.app.state.event_service
    credits = postgres_client.app.state.credit_service
    events.claim(USER_B, event_id)
    before = credits.balance(USER_A)

    with pytest.raises(AppError) as excinfo:
        events.claim(USER_A, event_id)

    assert excinfo.value.code == "EVENT_FULL"
    assert credits.balance(USER_A) == before


def test_the_listing_resolves_claim_state_on_postgres(
    postgres_client: TestClient, postgres_url: str
) -> None:
    event_id = seed_event(postgres_url, bonus=7, max_claims=5)
    events = postgres_client.app.state.event_service

    before = next(row for row in events.list_for(USER_A) if row["id"] == event_id)
    assert before["claimable"] is True
    assert before["remaining_slots"] == 5

    events.claim(USER_A, event_id)

    after = next(row for row in events.list_for(USER_A) if row["id"] == event_id)
    assert after["claimable"] is False
    assert after["claimed_this_period"] is True
    assert after["remaining_slots"] == 4


def test_an_active_discount_is_found_on_postgres(
    postgres_client: TestClient, postgres_url: str
) -> None:
    with psycopg.connect(postgres_url, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO public.events (code, name, kind, discount_percent, recurrence, "
            " starts_at, ends_at, is_active) VALUES "
            "('PG_DISCOUNT', 'Hot', 'discount', 40, 'once', now() - interval '1 hour', "
            " now() + interval '1 hour', true)"
        )

    assert postgres_client.app.state.event_service.discount_percent() == 40
