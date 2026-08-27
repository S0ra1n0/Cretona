from __future__ import annotations

import json
import random
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from app.repository import (
    AuditEntry,
    InsufficientCreditsError,
    UnknownUserError,
    UsernameTakenError,
    build_stats,
    decode_cursor,
    encode_cursor,
    reject_immutable_columns,
)

USER_COLUMNS = (
    "u.id, u.email, u.username, u.avatar_path, u.gender, u.birthday, "
    "u.is_disabled, u.created_at, r.name AS role"
)

# The Supabase table spells the owner `user_id` and lives under a different
# name. Adapters own this translation so ProjectService never learns it.
TABLE = "public.video_projects"
SERVICE_TO_DB = {"owner_id": "user_id"}
DB_TO_SERVICE = {value: key for key, value in SERVICE_TO_DB.items()}

# Split by the migration that introduced them so a startup failure can name the
# file to apply. Rows come back through `dict_row`, so the order is cosmetic.
BASELINE_COLUMNS = (
    "id, user_id, title, prompt, image_path, provider, status, provider_job_id, "
    "error_code, error_message, duration_seconds, aspect_ratio, video_path, "
    "thumbnail_path, poll_count, attempt_count, idempotency_key, started_at, "
    "lease_owner, lease_expires_at, created_at, updated_at, completed_at"
)
PROGRESS_COLUMNS = "progress_percent, step_message"
SELECTED_COLUMNS = f"{BASELINE_COLUMNS}, {PROGRESS_COLUMNS}"


class SchemaMismatchError(RuntimeError):
    """The target database is missing what the adapter needs."""


class PostgresDatabase:
    """Supabase/Postgres adapter.

    Deliberately never issues DDL. The remote schema is owned by
    `supabase/bootstrap.sql` and its numbered migrations; a backend that could
    silently alter it would make an unreviewed production migration a
    deployment side effect.
    """

    backend = "postgres"

    def __init__(self, dsn: str, *, min_size: int = 1, max_size: int = 8) -> None:
        self.pool = ConnectionPool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
            open=False,
        )

    def initialize(self) -> None:
        self.pool.open()
        self.pool.wait(timeout=30)
        # Fail at startup with a precise message rather than on the first user
        # request with an opaque one.
        try:
            with self.pool.connection() as connection:
                connection.execute(f"SELECT {BASELINE_COLUMNS} FROM {TABLE} LIMIT 0")
        except psycopg.errors.UndefinedTable as exc:
            raise SchemaMismatchError(
                f"{TABLE} is missing. Apply supabase/bootstrap.sql first."
            ) from exc
        except psycopg.errors.UndefinedColumn as exc:
            raise SchemaMismatchError(
                f"{TABLE} is missing a column this backend needs. Apply "
                "supabase/002_add_error_code.sql, "
                "supabase/003_add_fastapi_parity_columns.sql, "
                "supabase/004_add_started_at.sql, and "
                "supabase/005_add_poll_lease.sql."
            ) from exc

        # 009 in two halves, because it changed two things and the columns can
        # be present while the constraint is not: a database that took the
        # `add column if not exists` but kept the old `chk_error_code` accepts
        # every progress update and rejects every cancellation.
        try:
            with self.pool.connection() as connection:
                connection.execute(f"SELECT {PROGRESS_COLUMNS} FROM {TABLE} LIMIT 0")
        except psycopg.errors.UndefinedColumn as exc:
            raise SchemaMismatchError(
                f"{TABLE} is missing progress tracking columns. Apply "
                "supabase/009_add_progress_tracking.sql."
            ) from exc

        with self.pool.connection() as connection:
            row = connection.execute(
                "SELECT pg_get_constraintdef(oid) AS definition FROM pg_constraint "
                "WHERE conrelid = %s::regclass AND conname = 'chk_error_code'",
                (TABLE,),
            ).fetchone()
        # No constraint at all means nothing rejects the value. Only a
        # constraint that exists and omits 'cancelled' is a mismatch.
        if row is not None and "cancelled" not in row["definition"]:
            raise SchemaMismatchError(
                f"chk_error_code on {TABLE} rejects the 'cancelled' error code "
                "that cancellation writes. Apply "
                "supabase/009_add_progress_tracking.sql."
            )

        try:
            with self.pool.connection() as connection:
                connection.execute(
                    "SELECT caller_key, bucket, occurred_at FROM public.rate_limit_hits LIMIT 0"
                )
        except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn) as exc:
            raise SchemaMismatchError(
                "public.rate_limit_hits is missing or incompatible. Apply "
                "supabase/007_add_shared_rate_limits.sql."
            ) from exc

        # Checked at startup for the same reason as the others: an admin
        # discovering the table is missing by way of a 500 mid-change is a
        # worse failure than the service refusing to boot.
        try:
            with self.pool.connection() as connection:
                connection.execute(
                    "SELECT id, actor_id, action, target_type, target_id, details, created_at "
                    "FROM public.admin_audit_logs LIMIT 0"
                )
        except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn) as exc:
            raise SchemaMismatchError(
                "public.admin_audit_logs is missing or incompatible. Apply "
                "supabase/008_add_admin_audit_logs.sql."
            ) from exc

        # Named separately so a missing avatar column reports the migration that
        # adds it, rather than surfacing as a confusing failure on /me.
        try:
            with self.pool.connection() as connection:
                connection.execute("SELECT avatar_path FROM public.users LIMIT 0")
        except psycopg.errors.UndefinedColumn as exc:
            raise SchemaMismatchError(
                "public.users is missing avatar_path. Apply supabase/010_add_user_avatar.sql."
            ) from exc

        try:
            with self.pool.connection() as connection:
                connection.execute("SELECT gender, birthday FROM public.users LIMIT 0")
        except psycopg.errors.UndefinedColumn as exc:
            raise SchemaMismatchError(
                "public.users is missing gender or birthday. Apply "
                "supabase/012_add_user_profile_fields.sql."
            ) from exc

    def close(self) -> None:
        self.pool.close()

    # --- rate limiting -------------------------------------------------------

    # T3-3: the read/prune/count/insert cycle used to be four sequential round
    # trips after the lock, plus an unconditional fifth for the global sweep --
    # measured against a live pooler at ~190ms/trip, that is most of a second
    # spent on one rate-limit check. The sweep exists to bound the table for
    # callers who never come back and make their own prune moot; it has no
    # per-request correctness role, so it does not need to run on every
    # request to do its job -- only often enough, in aggregate, across all
    # traffic. Sampling it here is the same trade the retention sweep and the
    # request-log sampler already make elsewhere in this codebase.
    RATE_LIMIT_SWEEP_SAMPLE_RATE = 0.02

    _CONSUME_SQL = """
        WITH now_ts AS MATERIALIZED (
            SELECT clock_timestamp() AS now
        ),
        pruned AS (
            -- This caller's own expired hits. Bounded by construction: a
            -- caller can never hold more than `limit` rows for one bucket,
            -- because the insert below only happens when count < limit.
            DELETE FROM public.rate_limit_hits
            WHERE caller_key = %(key)s AND bucket = %(bucket)s
              AND occurred_at <= (SELECT now FROM now_ts)
                                  - (%(window_seconds)s * interval '1 second')
            RETURNING id
        ),
        remaining AS MATERIALIZED (
            -- Sibling CTEs share one MVCC snapshot, so this SELECT cannot see
            -- `pruned`'s DELETE directly -- excluding its returned ids by hand
            -- is what makes the count reflect the post-prune state within a
            -- single statement, rather than re-reading after a second trip.
            SELECT count(*) AS used
            FROM public.rate_limit_hits h
            WHERE h.caller_key = %(key)s AND h.bucket = %(bucket)s
              AND NOT EXISTS (SELECT 1 FROM pruned p WHERE p.id = h.id)
        ),
        inserted AS (
            INSERT INTO public.rate_limit_hits (caller_key, bucket, occurred_at)
            SELECT %(key)s, %(bucket)s, (SELECT now FROM now_ts)
            WHERE (SELECT used FROM remaining) < %(limit)s
            RETURNING 1
        )
        SELECT
            (SELECT now FROM now_ts) AS now,
            (SELECT used FROM remaining) AS used,
            EXISTS (SELECT 1 FROM inserted) AS did_insert
    """

    _SWEEP_SQL = """
        WITH expired AS (
            SELECT id FROM public.rate_limit_hits
            WHERE occurred_at <= %s::timestamptz - (%s * interval '1 second')
            ORDER BY occurred_at ASC, id ASC LIMIT 1000
            FOR UPDATE SKIP LOCKED
        ) DELETE FROM public.rate_limit_hits hits
        USING expired WHERE hits.id = expired.id
    """

    def consume_rate_limit(
        self,
        key: str,
        bucket: str,
        limit: int,
        window_seconds: float,
    ) -> tuple[bool, int]:
        """Atomically consume one slot in a shared sliding window.

        Two round trips in the common case: the advisory lock, then one
        statement that reads the clock, prunes this caller's expired hits,
        counts what remains, and inserts if there is room. A third, sampled
        trip occasionally sweeps other callers' expired rows.

        The lock is acquired on its own, before anything else, exactly as
        before -- this is transaction-scoped and serializes only this caller
        and bucket across API instances, and that guarantee must not become
        entangled with assumptions about CTE evaluation order. Everything
        after it runs already holding the lock, so no ordering question
        remains for the combined statement: no concurrent transaction for this
        caller and bucket can be interleaved with it.
        """
        with self.pool.connection() as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"{key}\x1f{bucket}",),
            )
            row = connection.execute(
                self._CONSUME_SQL,
                {"key": key, "bucket": bucket, "window_seconds": window_seconds, "limit": limit},
            ).fetchone()
            if row is None:  # pragma: no cover - SELECT always returns one row
                raise RuntimeError("Rate limit statement returned no row.")
            now, used, allowed = row["now"], int(row["used"]), bool(row["did_insert"])
            if allowed:
                used += 1

            if random.random() < self.RATE_LIMIT_SWEEP_SAMPLE_RATE:
                connection.execute(self._SWEEP_SQL, (now, window_seconds))

        return allowed, max(0, limit - used)

    # --- users ---------------------------------------------------------------

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        if not _is_uuid(user_id):
            return None
        with self.pool.connection() as connection:
            row = connection.execute(
                f"SELECT {USER_COLUMNS} FROM public.users u "
                "JOIN public.roles r ON r.id = u.role_id WHERE u.id = %s",
                (user_id,),
            ).fetchone()
        return _to_user(row)

    def sync_user_email(self, user_id: str, email: str) -> None:
        """Record the email a verified token claims for this account.

        The signup trigger writes the row once and never revisits it, so a
        changed address never reached this table. Written only when it
        actually differs, so the common request does no write.
        """
        if not _is_uuid(user_id):
            return
        with self.pool.connection() as connection:
            connection.execute(
                "UPDATE public.users SET email = %s WHERE id = %s "
                "AND (email IS NULL OR email <> %s)",
                (email, user_id, email),
            )

    def set_username(self, user_id: str, username: str | None) -> dict[str, Any] | None:
        return self.update_profile(user_id, username=username)

    def update_profile(
        self,
        user_id: str,
        *,
        username: str | None = None,
        avatar_path: str | None = None,
        set_avatar: bool = False,
        gender: str | None = None,
        set_gender: bool = False,
        birthday: str | None = None,
        set_birthday: bool = False,
    ) -> dict[str, Any] | None:
        """Write the profile fields in one statement.

        Each `set_*` flag distinguishes "leave this alone" from "clear it":
        both arrive as `None`, and without the flag a rename would silently
        wipe the picture, the gender and the birthday.
        """
        if not _is_uuid(user_id):
            return None

        assignments = ["username = %s"]
        parameters: list[Any] = [username]
        if set_avatar:
            assignments.append("avatar_path = %s")
            parameters.append(avatar_path)
        if set_gender:
            assignments.append("gender = %s")
            parameters.append(gender)
        if set_birthday:
            assignments.append("birthday = %s")
            parameters.append(birthday)
        parameters.append(user_id)

        try:
            with self.pool.connection() as connection:
                changed = connection.execute(
                    f"UPDATE public.users SET {', '.join(assignments)} WHERE id = %s",
                    tuple(parameters),
                ).rowcount
        except pg_errors.UniqueViolation as exc:
            raise UsernameTakenError(username) from exc
        return self.get_user(user_id) if changed else None

    def list_users(
        self,
        *,
        limit: int,
        cursor: str | None,
        query: str | None,
        role: str | None,
        is_disabled: bool | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        where = ["TRUE"]
        parameters: list[Any] = []

        if query:
            where.append("(u.email ILIKE %s OR u.username ILIKE %s)")
            pattern = f"%{query}%"
            parameters.extend([pattern, pattern])
        if role:
            where.append("r.name = %s")
            parameters.append(role)
        if is_disabled is not None:
            where.append("u.is_disabled = %s")
            parameters.append(is_disabled)
        if cursor:
            created_at, user_id = decode_cursor(cursor)
            if not _is_uuid(user_id):
                raise ValueError("Invalid cursor")
            where.append(
                "(u.created_at < %s::timestamptz "
                "OR (u.created_at = %s::timestamptz AND u.id < %s::uuid))"
            )
            parameters.extend([created_at, created_at, user_id])

        parameters.append(limit + 1)
        with self.pool.connection() as connection:
            rows = connection.execute(
                f"SELECT {USER_COLUMNS}, "
                "(SELECT COUNT(*) FROM public.video_projects p "
                " WHERE p.user_id = u.id AND p.deleted_at IS NULL) AS project_count "
                "FROM public.users u JOIN public.roles r ON r.id = u.role_id "
                "WHERE " + " AND ".join(where) + " "
                "ORDER BY u.created_at DESC, u.id DESC LIMIT %s",
                tuple(parameters),
            ).fetchall()

        users = [user for user in (_to_user(row) for row in rows) if user]
        items = users[:limit]
        next_cursor = None
        if len(users) > limit and items:
            next_cursor = encode_cursor(items[-1]["created_at"], items[-1]["id"])
        return items, next_cursor

    def update_user_flags(
        self,
        user_id: str,
        *,
        role: str | None = None,
        is_disabled: bool | None = None,
        audit: AuditEntry | None = None,
    ) -> dict[str, Any] | None:
        if not _is_uuid(user_id):
            return None

        assignments: list[str] = []
        parameters: list[Any] = []
        if role is not None:
            # Resolved as a subquery so an unknown role name fails the write
            # rather than silently leaving the row unchanged.
            assignments.append("role_id = (SELECT id FROM public.roles WHERE name = %s)")
            parameters.append(role)
        if is_disabled is not None:
            assignments.append("is_disabled = %s")
            parameters.append(is_disabled)
        if not assignments:
            return self.get_user(user_id)

        parameters.append(user_id)
        with self.pool.connection() as connection, connection.transaction():
            # One transaction, so a privilege change cannot commit without its
            # audit row and an unwritable audit table cannot let one through
            # unrecorded (T2-5).
            changed = connection.execute(
                f"UPDATE public.users SET {', '.join(assignments)} WHERE id = %s",
                tuple(parameters),
            ).rowcount
            if changed and audit is not None:
                self._insert_audit_log(connection, audit)
        return self.get_user(user_id) if changed else None

    def count_enabled_admins(self) -> int:
        with self.pool.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM public.users u "
                "JOIN public.roles r ON r.id = u.role_id "
                "WHERE r.name = 'admin' AND NOT u.is_disabled"
            ).fetchone()
        return int(row["total"] or 0) if row else 0

    def admin_stats(self, since: str) -> dict[str, Any]:
        with self.pool.connection() as connection:
            totals = connection.execute(
                "SELECT (SELECT COUNT(*) FROM public.users) AS users, "
                "(SELECT COUNT(*) FROM public.users WHERE NOT is_disabled) AS active_users, "
                "(SELECT COUNT(*) FROM public.video_projects "
                " WHERE deleted_at IS NULL) AS projects"
            ).fetchone()
            by_status = connection.execute(
                "SELECT status::text AS status, COUNT(*) AS total "
                "FROM public.video_projects WHERE deleted_at IS NULL GROUP BY status"
            ).fetchall()
            by_provider = connection.execute(
                "SELECT provider, COUNT(*) AS total "
                "FROM public.video_projects WHERE deleted_at IS NULL GROUP BY provider"
            ).fetchall()
            daily = connection.execute(
                "SELECT date_trunc('day', created_at)::date AS date, COUNT(*) AS created, "
                "COUNT(*) FILTER (WHERE status = 'completed') AS completed, "
                "COUNT(*) FILTER (WHERE status = 'failed') AS failed "
                "FROM public.video_projects "
                "WHERE deleted_at IS NULL AND created_at >= %s::timestamptz "
                "GROUP BY 1 ORDER BY 1 DESC",
                (since,),
            ).fetchall()

        return build_stats(dict(totals), by_status, by_provider, daily)

    # --- projects ------------------------------------------------------------

    def create_project(self, values: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        payload = {SERVICE_TO_DB.get(key, key): value for key, value in values.items()}
        # `deleted_at` is not in the service payload; the column defaults to NULL.
        columns = ", ".join(payload)
        placeholders = ", ".join("%s" for _ in payload)
        try:
            with self.pool.connection() as connection:
                row = connection.execute(
                    f"INSERT INTO {TABLE} ({columns}) VALUES ({placeholders}) "
                    f"RETURNING {SELECTED_COLUMNS}",
                    tuple(payload.values()),
                ).fetchone()
        except pg_errors.UniqueViolation:
            key = values.get("idempotency_key")
            if not key:
                raise
            existing = self.find_by_idempotency(values["owner_id"], key)
            if existing is None:
                raise
            return existing, False

        if row is None:  # pragma: no cover - RETURNING always yields a row
            raise RuntimeError("Inserted project could not be read back.")
        return _to_service_row(row), True

    def find_by_idempotency(self, owner_id: str, key: str) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            row = connection.execute(
                f"SELECT {SELECTED_COLUMNS} FROM {TABLE} "
                "WHERE user_id = %s AND idempotency_key = %s AND deleted_at IS NULL",
                (owner_id, key),
            ).fetchone()
        return _to_service_row(row) if row else None

    def get_project(self, project_id: str, owner_id: str) -> dict[str, Any] | None:
        if not _is_uuid(project_id):
            return None
        with self.pool.connection() as connection:
            row = connection.execute(
                f"SELECT {SELECTED_COLUMNS} FROM {TABLE} "
                "WHERE id = %s AND user_id = %s AND deleted_at IS NULL",
                (project_id, owner_id),
            ).fetchone()
        return _to_service_row(row) if row else None

    def get_project_by_id(self, project_id: str) -> dict[str, Any] | None:
        if not _is_uuid(project_id):
            return None
        with self.pool.connection() as connection:
            row = connection.execute(
                f"SELECT {SELECTED_COLUMNS} FROM {TABLE} WHERE id = %s AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
        return _to_service_row(row) if row else None

    def find_by_provider_job_id(self, job_id: str) -> dict[str, Any] | None:
        with self.pool.connection() as connection:
            row = connection.execute(
                f"SELECT {SELECTED_COLUMNS} FROM {TABLE} "
                "WHERE provider_job_id = %s AND deleted_at IS NULL",
                (job_id,),
            ).fetchone()
        return _to_service_row(row) if row else None

    def update_project(
        self,
        project_id: str,
        owner_id: str,
        values: dict[str, Any],
        *,
        expected_status: str | None = None,
    ) -> dict[str, Any] | None:
        reject_immutable_columns(values)
        if not values:
            return self.get_project(project_id, owner_id)
        if not _is_uuid(project_id):
            return None

        assignments = ", ".join(f"{column} = %s" for column in values)
        parameters: list[Any] = [*values.values(), project_id, owner_id]
        status_clause = ""
        if expected_status is not None:
            status_clause = " AND status = %s"
            parameters.append(expected_status)

        with self.pool.connection() as connection:
            row = connection.execute(
                f"UPDATE {TABLE} SET {assignments} "
                f"WHERE id = %s AND user_id = %s AND deleted_at IS NULL{status_clause} "
                f"RETURNING {SELECTED_COLUMNS}",
                tuple(parameters),
            ).fetchone()
        return _to_service_row(row) if row else None

    def list_projects(
        self,
        owner_id: str,
        *,
        limit: int,
        status: str | None,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        where = ["user_id = %s", "deleted_at IS NULL"]
        parameters: list[Any] = [owner_id]

        if status:
            where.append("status = %s")
            parameters.append(status)

        if cursor:
            created_at, project_id = decode_cursor(cursor)
            if not _is_uuid(project_id):
                raise ValueError("Invalid cursor")
            where.append(
                "(created_at < %s::timestamptz OR (created_at = %s::timestamptz AND id < %s::uuid))"
            )
            parameters.extend([created_at, created_at, project_id])

        parameters.append(limit + 1)
        query = (
            f"SELECT {SELECTED_COLUMNS} FROM {TABLE} WHERE "
            + " AND ".join(where)
            + " ORDER BY created_at DESC, id DESC LIMIT %s"
        )
        with self.pool.connection() as connection:
            rows = [
                _to_service_row(row)
                for row in connection.execute(query, tuple(parameters)).fetchall()
            ]

        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(last["created_at"], last["id"])
        return items, next_cursor

    def claim_in_flight_projects(
        self,
        limit: int,
        *,
        owner: str,
        now: str,
        lease_until: str,
        providers: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Take a durable lease on a batch, skipping rows others hold.

        SKIP LOCKED still does the work of keeping two simultaneous claims from
        selecting the same rows, but the lease is what survives the
        transaction. The row lock is released as soon as this commits, and the
        provider calls that follow happen long after that.

        `providers` scopes the claim (W1). SKIP LOCKED stops two claimants
        picking the same row; it does not stop the wrong claimant picking a row
        it cannot execute. Disjoint provider sets do.
        """
        provider_filter = ""
        provider_args: tuple[Any, ...] = ()
        if providers is not None:
            if not providers:
                # An empty set means "this claimant runs nothing", not "no
                # filter". Returning early is the difference between claiming
                # nothing and claiming everything.
                return []
            provider_filter = "     AND provider = ANY(%s) "
            provider_args = (list(providers),)

        with self.pool.connection() as connection:
            rows = connection.execute(
                f"UPDATE {TABLE} SET lease_owner = %s, lease_expires_at = %s::timestamptz "
                "WHERE id IN ("
                f"  SELECT id FROM {TABLE} "
                "   WHERE status IN ('pending', 'generating') AND deleted_at IS NULL "
                "     AND (lease_expires_at IS NULL OR lease_expires_at < %s::timestamptz) "
                f"{provider_filter}"
                "   ORDER BY updated_at ASC LIMIT %s FOR UPDATE SKIP LOCKED"
                f") RETURNING {SELECTED_COLUMNS}",
                (owner, lease_until, now, *provider_args, limit),
            ).fetchall()
        return [_to_service_row(row) for row in rows]

    def release_lease(self, project_id: str, owner: str) -> None:
        """Scoped to the owner, so an expired holder cannot clear a new claim."""
        if not _is_uuid(project_id):
            return
        with self.pool.connection() as connection:
            connection.execute(
                f"UPDATE {TABLE} SET lease_owner = NULL, lease_expires_at = NULL "
                "WHERE id = %s AND lease_owner = %s",
                (project_id, owner),
            )

    def record_generation_log(self, values: dict[str, Any]) -> None:
        if not _is_uuid(values["project_id"]):
            return
        with self.pool.connection() as connection:
            connection.execute(
                "INSERT INTO public.generation_logs "
                "(project_id, provider, request_id, event, request, response, http_status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    values["project_id"],
                    values["provider"],
                    values.get("request_id"),
                    values["event"],
                    Json(values["request"]) if values.get("request") is not None else None,
                    Json(values["response"]) if values.get("response") is not None else None,
                    values.get("http_status"),
                ),
            )

    def generation_logs(self, project_id: str) -> list[dict[str, Any]]:
        if not _is_uuid(project_id):
            return []
        with self.pool.connection() as connection:
            rows = connection.execute(
                "SELECT id, project_id, provider, request_id, event, request, response, "
                "http_status, created_at FROM public.generation_logs "
                "WHERE project_id = %s ORDER BY created_at ASC, id ASC",
                (project_id,),
            ).fetchall()
        return [_to_service_row(row) for row in rows]

    def list_projects_missing_thumbnails(self) -> list[dict[str, Any]]:
        with self.pool.connection() as connection:
            rows = connection.execute(
                "SELECT id, user_id, title, prompt, image_path, provider, "
                "status, provider_job_id, error_code, error_message, "
                "duration_seconds, aspect_ratio, video_path, thumbnail_path, "
                "poll_count, attempt_count, idempotency_key, started_at, "
                "created_at, updated_at, completed_at, deleted_at "
                "FROM public.video_projects "
                "WHERE status = 'completed' AND video_path IS NOT NULL "
                "AND (thumbnail_path IS NULL OR thumbnail_path = '') "
                "AND deleted_at IS NULL"
            ).fetchall()
        return [_to_service_row(row) for row in rows]

    def prune_generation_logs(self, before: str, limit: int) -> list[dict[str, Any]]:
        """Delete one disjoint batch, safe when several instances sweep.

        `SKIP LOCKED` prevents two workers from summarizing the same rows. The
        delete and its metadata-only RETURNING projection share one
        transaction; raw request/response JSON never leaves the database.
        """
        with self.pool.connection() as connection:
            rows = connection.execute(
                "WITH candidates AS ("
                "  SELECT id FROM public.generation_logs "
                "  WHERE created_at < %s::timestamptz "
                "  ORDER BY created_at ASC, id ASC LIMIT %s "
                "  FOR UPDATE SKIP LOCKED"
                "), deleted AS ("
                "  DELETE FROM public.generation_logs logs "
                "  USING candidates WHERE logs.id = candidates.id "
                "  RETURNING logs.provider, logs.event, logs.http_status"
                ") SELECT provider, event, http_status FROM deleted",
                (before, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_quota_usage(
        self,
        owner_id: str,
        since: str,
        not_charged: tuple[str, ...],
    ) -> tuple[int, str | None]:
        with self.pool.connection() as connection:
            row = connection.execute(
                "SELECT COALESCE("
                "SUM(CASE WHEN provider IN ('real', 'wan21', 'cloud', 'local') "
                "OR duration_seconds > 5 THEN 2 ELSE 1 END), "
                f"0) AS used, MIN(created_at) AS oldest FROM {TABLE} "
                "WHERE user_id = %s AND created_at >= %s::timestamptz "
                "AND deleted_at IS NULL "
                "AND (error_code IS NULL OR NOT (error_code = ANY(%s)))",
                (owner_id, since, list(not_charged)),
            ).fetchone()
        if row is None:  # pragma: no cover - an aggregate always returns a row
            return 0, None
        oldest = row["oldest"]
        if isinstance(oldest, datetime):
            oldest = oldest.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return int(row["used"] or 0), oldest

    def soft_delete_project(self, project_id: str, owner_id: str, deleted_at: str) -> bool:
        if not _is_uuid(project_id):
            return False
        with self.pool.connection() as connection:
            cursor = connection.execute(
                f"UPDATE {TABLE} SET deleted_at = %s "
                "WHERE id = %s AND user_id = %s AND deleted_at IS NULL",
                (deleted_at, project_id, owner_id),
            )
        return cursor.rowcount > 0

    @staticmethod
    def _insert_audit_log(connection: psycopg.Connection[Any], entry: AuditEntry) -> None:
        """The INSERT alone, on a caller-supplied connection.

        Kept separate so a mutation can enlist it in its own transaction rather
        than taking a second connection that commits independently.
        """
        connection.execute(
            "INSERT INTO public.admin_audit_logs ("
            "id, actor_id, action, target_type, target_id, details, created_at"
            ") VALUES (%s, %s, %s, %s, %s, %s, %s::timestamptz)",
            (
                entry.id,
                entry.actor_id,
                entry.action,
                entry.target_type,
                entry.target_id,
                # Json, not json.dumps: the column is jsonb, and sending a
                # string would either be rejected or stored as JSON text.
                Json(entry.details) if entry.details is not None else None,
                entry.created_at,
            ),
        )

    def insert_audit_log(
        self,
        *,
        id: str,
        actor_id: str,
        action: str,
        target_type: str,
        target_id: str | None = None,
        details: Any = None,
        created_at: str,
    ) -> dict[str, Any]:
        with self.pool.connection() as connection:
            self._insert_audit_log(
                connection,
                AuditEntry(
                    id=id,
                    actor_id=actor_id,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    details=details,
                    created_at=created_at,
                ),
            )
        return {
            "id": id,
            "actor_id": actor_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "details": details,
            "created_at": created_at,
        }

    def list_audit_logs(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        action: str | None = None,
        actor_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        clauses: list[str] = []
        params: list[Any] = []
        if action:
            clauses.append("action = %s")
            params.append(action)
        if actor_id:
            clauses.append("actor_id = %s")
            params.append(actor_id)
        if cursor:
            cursor_created_at, cursor_id = decode_cursor(cursor)
            clauses.append(
                "(created_at < %s::timestamptz OR (created_at = %s::timestamptz AND id < %s))"
            )
            params.extend([cursor_created_at, cursor_created_at, cursor_id])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            f"SELECT * FROM public.admin_audit_logs {where_sql} "
            "ORDER BY created_at DESC, id DESC LIMIT %s"
        )
        params.append(limit + 1)
        with self.pool.connection() as connection:
            rows = [dict(row) for row in connection.execute(query, tuple(params)).fetchall()]

        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            last_created = last["created_at"]
            if isinstance(last_created, datetime):
                last_created = last_created.astimezone(UTC).isoformat().replace("+00:00", "Z")
            next_cursor = encode_cursor(last_created, str(last["id"]))

        entries = []
        for row in rows:
            created_at = row["created_at"]
            if isinstance(created_at, datetime):
                created_at = created_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
            details = row.get("details")
            if isinstance(details, str):
                details = json.loads(details)
            entries.append(
                {
                    "id": str(row["id"]),
                    "actor_id": str(row["actor_id"]),
                    "action": row["action"],
                    "target_type": row["target_type"],
                    "target_id": str(row["target_id"]) if row.get("target_id") else None,
                    "details": details,
                    "created_at": created_at,
                }
            )
        return entries, next_cursor


    # --- credits -------------------------------------------------------------

    def get_setting(self, key: str) -> str | None:
        with self.pool.connection() as connection:
            row = connection.execute(
                "SELECT value FROM public.settings WHERE key = %s", (key,)
            ).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str, *, updated_by: str, updated_at: str) -> None:
        with self.pool.connection() as connection:
            connection.execute(
                "INSERT INTO public.settings (key, value, updated_by, updated_at) "
                "VALUES (%s, %s, %s, %s::timestamptz) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value, "
                "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
                (key, value, updated_by if _is_uuid(updated_by) else None, updated_at),
            )

    def get_credit_balance(self, user_id: str) -> int | None:
        if not _is_uuid(user_id):
            return None
        with self.pool.connection() as connection:
            row = connection.execute(
                "SELECT credit_balance FROM public.users WHERE id = %s", (user_id,)
            ).fetchone()
        return int(row["credit_balance"]) if row else None

    def apply_credit_delta(
        self,
        *,
        transaction_id: str,
        user_id: str,
        delta: int,
        reason: str,
        created_at: str,
        ref_type: str | None = None,
        ref_id: str | None = None,
        note: str | None = None,
        idempotency_key: str | None = None,
        audit: AuditEntry | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Move a balance and write its ledger row in one transaction.

        The `credit_balance + %s >= 0` guard lives in the UPDATE rather than in
        a prior SELECT: read-then-write loses to a concurrent charge, and the
        thing it loses is money.

        Returns `(row, created)`. `created` is False when `idempotency_key` was
        already used -- the original row comes back and nothing moved.
        """
        if not _is_uuid(user_id):
            raise UnknownUserError(user_id)
        try:
            with self.pool.connection() as connection, connection.transaction():
                updated = connection.execute(
                    "UPDATE public.users SET credit_balance = credit_balance + %s "
                    "WHERE id = %s AND credit_balance + %s >= 0 "
                    "RETURNING credit_balance",
                    (delta, user_id, delta),
                ).fetchone()
                if updated is None:
                    exists = connection.execute(
                        "SELECT 1 FROM public.users WHERE id = %s", (user_id,)
                    ).fetchone()
                    raise (
                        InsufficientCreditsError(user_id)
                        if exists
                        else UnknownUserError(user_id)
                    )

                row = connection.execute(
                    "INSERT INTO public.credit_transactions "
                    "(id, user_id, delta, balance_after, reason, ref_type, ref_id, "
                    " note, idempotency_key, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::timestamptz) "
                    "RETURNING *",
                    (
                        transaction_id, user_id, delta, int(updated["credit_balance"]),
                        reason, ref_type, ref_id, note, idempotency_key, created_at,
                    ),
                ).fetchone()
                if audit is not None:
                    # Same transaction as the money it describes (T2-5).
                    self._insert_audit_log(connection, audit)
        except pg_errors.UniqueViolation:
            if not idempotency_key:
                raise
            existing = self.find_credit_transaction_by_key(user_id, idempotency_key)
            if existing is None:
                raise
            return existing, False

        if row is None:  # pragma: no cover - just inserted
            raise RuntimeError("Inserted credit transaction could not be read back.")
        return _to_credit_row(row), True

    # --- packages and payments -----------------------------------------------

    def list_credit_packages(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM public.credit_packages"
        if active_only:
            query += " WHERE is_active"
        query += " ORDER BY sort_order ASC, credits ASC"
        with self.pool.connection() as connection:
            rows = connection.execute(query).fetchall()
        return [_payment_like_row(row) for row in rows]

    def get_credit_package(self, package_id: str) -> dict[str, Any] | None:
        if not _is_uuid(package_id):
            return None
        with self.pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM public.credit_packages WHERE id = %s", (package_id,)
            ).fetchone()
        return _payment_like_row(row) if row else None

    def find_payment_by_key(
        self, user_id: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        if not _is_uuid(user_id):
            return None
        with self.pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM public.payments "
                "WHERE user_id = %s AND idempotency_key = %s",
                (user_id, idempotency_key),
            ).fetchone()
        return _payment_like_row(row) if row else None

    def record_payment(
        self,
        *,
        payment_id: str,
        transaction_id: str,
        user_id: str,
        package_id: str,
        amount_vnd: int,
        credits_granted: int,
        method: str,
        idempotency_key: str | None,
        created_at: str,
    ) -> tuple[dict[str, Any], bool]:
        """Complete a purchase and grant its credits in one transaction.

        Contract §8.2. Neither half can land without the other.
        """
        if not _is_uuid(user_id):
            raise UnknownUserError(user_id)
        try:
            with self.pool.connection() as connection, connection.transaction():
                updated = connection.execute(
                    "UPDATE public.users SET credit_balance = credit_balance + %s "
                    "WHERE id = %s RETURNING credit_balance",
                    (credits_granted, user_id),
                ).fetchone()
                if updated is None:
                    raise UnknownUserError(user_id)

                row = connection.execute(
                    "INSERT INTO public.payments (id, user_id, package_id, amount_vnd, "
                    " credits_granted, method, status, idempotency_key, created_at, "
                    " completed_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, 'completed', %s, "
                    "        %s::timestamptz, %s::timestamptz) RETURNING *",
                    (
                        payment_id, user_id, package_id, amount_vnd, credits_granted,
                        method, idempotency_key, created_at, created_at,
                    ),
                ).fetchone()
                connection.execute(
                    "INSERT INTO public.credit_transactions "
                    "(id, user_id, delta, balance_after, reason, ref_type, ref_id, "
                    " idempotency_key, created_at) "
                    "VALUES (%s, %s, %s, %s, 'purchase', 'payment', %s, %s, "
                    "        %s::timestamptz)",
                    (
                        transaction_id, user_id, credits_granted,
                        int(updated["credit_balance"]), payment_id,
                        f"purchase:{payment_id}", created_at,
                    ),
                )
        except pg_errors.UniqueViolation:
            if not idempotency_key:
                raise
            existing = self.find_payment_by_key(user_id, idempotency_key)
            if existing is None:
                raise
            return existing, False

        if row is None:  # pragma: no cover - just inserted
            raise RuntimeError("Inserted payment could not be read back.")
        return _payment_like_row(row), True

    # --- events --------------------------------------------------------------

    def list_events(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM public.events"
        if active_only:
            query += " WHERE is_active"
        query += " ORDER BY starts_at ASC, code ASC"
        with self.pool.connection() as connection:
            rows = connection.execute(query).fetchall()
        return [_event_row_pg(row) for row in rows]

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        if not _is_uuid(event_id):
            return None
        with self.pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM public.events WHERE id = %s", (event_id,)
            ).fetchone()
        return _event_row_pg(row) if row else None

    def count_event_claims(self, event_id: str) -> int:
        if not _is_uuid(event_id):
            return 0
        with self.pool.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM public.event_claims WHERE event_id = %s",
                (event_id,),
            ).fetchone()
        return int(row["n"])

    def claimed_periods(self, user_id: str, event_ids: Sequence[str]) -> set[tuple[str, str]]:
        ids = [value for value in event_ids if _is_uuid(value)]
        if not ids or not _is_uuid(user_id):
            return set()
        with self.pool.connection() as connection:
            rows = connection.execute(
                "SELECT event_id, period_key FROM public.event_claims "
                "WHERE user_id = %s AND event_id = ANY(%s)",
                (user_id, ids),
            ).fetchall()
        return {(str(row["event_id"]), row["period_key"]) for row in rows}

    def claim_event(
        self,
        *,
        claim_id: str,
        transaction_id: str,
        event_id: str,
        user_id: str,
        period_key: str,
        credits_granted: int,
        max_claims: int | None,
        created_at: str,
    ) -> tuple[dict[str, Any] | None, str]:
        """Take one claim and grant its credits, atomically.

        Returns `(row, status)`; status is `claimed`, `already` or `full`.
        The cap lives in the INSERT and the per-period rule in the unique
        index, because counting first and writing second loses a race that
        costs campaign budget.
        """
        if not _is_uuid(user_id) or not _is_uuid(event_id):
            raise UnknownUserError(user_id)

        with self.pool.connection() as connection, connection.transaction():
            if max_claims is None:
                cursor = connection.execute(
                    "INSERT INTO public.event_claims "
                    "(id, event_id, user_id, period_key, credits_granted, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s::timestamptz) "
                    "ON CONFLICT DO NOTHING RETURNING *",
                    (claim_id, event_id, user_id, period_key, credits_granted, created_at),
                )
            else:
                cursor = connection.execute(
                    "INSERT INTO public.event_claims "
                    "(id, event_id, user_id, period_key, credits_granted, created_at) "
                    "SELECT %s, %s, %s, %s, %s, %s::timestamptz "
                    "WHERE (SELECT COUNT(*) FROM public.event_claims "
                    "       WHERE event_id = %s) < %s "
                    "ON CONFLICT DO NOTHING RETURNING *",
                    (
                        claim_id, event_id, user_id, period_key, credits_granted,
                        created_at, event_id, max_claims,
                    ),
                )
            row = cursor.fetchone()

            if row is None:
                existing = connection.execute(
                    "SELECT 1 FROM public.event_claims "
                    "WHERE event_id = %s AND user_id = %s AND period_key = %s",
                    (event_id, user_id, period_key),
                ).fetchone()
                return None, "already" if existing else "full"

            updated = connection.execute(
                "UPDATE public.users SET credit_balance = credit_balance + %s "
                "WHERE id = %s RETURNING credit_balance",
                (credits_granted, user_id),
            ).fetchone()
            if updated is None:
                raise UnknownUserError(user_id)

            connection.execute(
                "INSERT INTO public.credit_transactions "
                "(id, user_id, delta, balance_after, reason, ref_type, ref_id, "
                " idempotency_key, created_at) "
                "VALUES (%s, %s, %s, %s, 'event_grant', 'event', %s, %s, "
                "        %s::timestamptz)",
                (
                    transaction_id, user_id, credits_granted,
                    int(updated["credit_balance"]), event_id,
                    f"claim:{event_id}:{user_id}:{period_key}", created_at,
                ),
            )

        return _payment_like_row(row), "claimed"

    # --- admin: credits, packages, events, payments ---------------------------

    def list_all_credit_transactions(
        self, *, limit: int, cursor: str | None = None, reason: str | None = None
    ) -> tuple[list[dict[str, Any]], str | None]:
        where: list[str] = []
        parameters: list[Any] = []
        if reason:
            where.append("reason = %s")
            parameters.append(reason)
        if cursor:
            created_at, row_id = decode_cursor(cursor)
            where.append(
                "(created_at < %s::timestamptz "
                " OR (created_at = %s::timestamptz AND id < %s::uuid))"
            )
            parameters.extend([created_at, created_at, row_id])

        clause = (" WHERE " + " AND ".join(where)) if where else ""
        parameters.append(limit + 1)
        with self.pool.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM public.credit_transactions" + clause
                + " ORDER BY created_at DESC, id DESC LIMIT %s",
                tuple(parameters),
            ).fetchall()

        items = [_to_credit_row(row) for row in rows]
        next_cursor = None
        if len(items) > limit:
            items = items[:limit]
            next_cursor = encode_cursor(items[-1]["created_at"], items[-1]["id"])
        return items, next_cursor

    def create_credit_package(
        self,
        *,
        package_id: str,
        name: str,
        credits: int,
        price_vnd: int,
        sort_order: int,
        created_at: str,
        audit: AuditEntry | None = None,
    ) -> dict[str, Any]:
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "INSERT INTO public.credit_packages "
                "(id, name, credits, price_vnd, sort_order, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s::timestamptz) RETURNING *",
                (package_id, name, credits, price_vnd, sort_order, created_at),
            ).fetchone()
            if audit is not None:
                self._insert_audit_log(connection, audit)
        return _payment_like_row(row)

    def update_credit_package(
        self, package_id: str, changes: dict[str, Any], *, audit: AuditEntry | None = None
    ) -> dict[str, Any] | None:
        if not _is_uuid(package_id):
            return None
        allowed = {"name", "credits", "price_vnd", "sort_order", "is_active"}
        fields = {key: value for key, value in changes.items() if key in allowed}
        if not fields:
            return self.get_credit_package(package_id)

        assignments = ", ".join(f"{key} = %s" for key in fields)
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                f"UPDATE public.credit_packages SET {assignments} "
                "WHERE id = %s RETURNING *",
                (*fields.values(), package_id),
            ).fetchone()
            if row is None:
                return None
            if audit is not None:
                self._insert_audit_log(connection, audit)
        return _payment_like_row(row)

    def create_event(
        self,
        *,
        event_id: str,
        values: dict[str, Any],
        created_at: str,
        audit: AuditEntry | None = None,
    ) -> dict[str, Any]:
        columns = (
            "code", "name", "description", "kind", "bonus_credits", "discount_percent",
            "recurrence", "active_days", "active_from_minute", "active_to_minute",
            "starts_at", "ends_at", "max_claims", "auto_grant", "is_active",
        )
        payload = {column: values.get(column) for column in columns}
        payload["auto_grant"] = bool(payload.get("auto_grant"))
        payload["is_active"] = payload.get("is_active", True) is not False
        casts = {"starts_at": "::timestamptz", "ends_at": "::timestamptz"}
        placeholders = ", ".join("%s" + casts.get(column, "") for column in columns)

        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "INSERT INTO public.events (id, created_at, "
                + ", ".join(columns)
                + ") VALUES (%s, %s::timestamptz, " + placeholders + ") RETURNING *",
                (event_id, created_at, *[payload[column] for column in columns]),
            ).fetchone()
            if audit is not None:
                self._insert_audit_log(connection, audit)
        return _event_row_pg(row)

    def update_event(
        self, event_id: str, changes: dict[str, Any], *, audit: AuditEntry | None = None
    ) -> dict[str, Any] | None:
        if not _is_uuid(event_id):
            return None
        allowed = {
            "name", "description", "bonus_credits", "discount_percent", "active_days",
            "active_from_minute", "active_to_minute", "starts_at", "ends_at",
            "max_claims", "is_active",
        }
        fields = {key: value for key, value in changes.items() if key in allowed}
        if not fields:
            return self.get_event(event_id)

        casts = {"starts_at": "::timestamptz", "ends_at": "::timestamptz"}
        assignments = ", ".join(
            f"{key} = %s" + casts.get(key, "") for key in fields
        )
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                f"UPDATE public.events SET {assignments} WHERE id = %s RETURNING *",
                (*fields.values(), event_id),
            ).fetchone()
            if row is None:
                return None
            if audit is not None:
                self._insert_audit_log(connection, audit)
        return _event_row_pg(row)

    def list_event_claims(self, event_id: str) -> list[dict[str, Any]]:
        if not _is_uuid(event_id):
            return []
        with self.pool.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM public.event_claims WHERE event_id = %s "
                "ORDER BY created_at DESC, id DESC",
                (event_id,),
            ).fetchall()
        return [_payment_like_row(row) for row in rows]

    def list_payments(
        self, *, status: str | None = None, limit: int = 20, cursor: str | None = None
    ) -> tuple[list[dict[str, Any]], str | None]:
        where: list[str] = []
        parameters: list[Any] = []
        if status:
            where.append("status = %s")
            parameters.append(status)
        if cursor:
            created_at, row_id = decode_cursor(cursor)
            where.append(
                "(created_at < %s::timestamptz "
                " OR (created_at = %s::timestamptz AND id < %s::uuid))"
            )
            parameters.extend([created_at, created_at, row_id])

        clause = (" WHERE " + " AND ".join(where)) if where else ""
        parameters.append(limit + 1)
        with self.pool.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM public.payments" + clause
                + " ORDER BY created_at DESC, id DESC LIMIT %s",
                tuple(parameters),
            ).fetchall()

        items = [_payment_like_row(row) for row in rows]
        next_cursor = None
        if len(items) > limit:
            items = items[:limit]
            next_cursor = encode_cursor(items[-1]["created_at"], items[-1]["id"])
        return items, next_cursor

    def list_all_projects(
        self,
        *,
        status: str | None = None,
        owner_id: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Every user's projects, for admin moderation.

        Separate from `list_projects` so the user-facing path never grows a
        flag whose only purpose is skipping the ownership check.
        """
        where = ["deleted_at IS NULL"]
        parameters: list[Any] = []
        if status:
            where.append("status = %s")
            parameters.append(status)
        if owner_id and _is_uuid(owner_id):
            where.append("user_id = %s")
            parameters.append(owner_id)
        if cursor:
            created_at, project_id = decode_cursor(cursor)
            where.append(
                "(created_at < %s::timestamptz "
                " OR (created_at = %s::timestamptz AND id < %s::uuid))"
            )
            parameters.extend([created_at, created_at, project_id])

        parameters.append(limit + 1)
        with self.pool.connection() as connection:
            rows = connection.execute(
                f"SELECT {SELECTED_COLUMNS} FROM {TABLE} WHERE "
                + " AND ".join(where)
                + " ORDER BY created_at DESC, id DESC LIMIT %s",
                tuple(parameters),
            ).fetchall()

        items = [_to_service_row(row) for row in rows]
        next_cursor = None
        if len(items) > limit:
            items = items[:limit]
            next_cursor = encode_cursor(items[-1]["created_at"], items[-1]["id"])
        return items, next_cursor

    def find_auto_grant_event(self, now: str) -> dict[str, Any] | None:
        """The active signup-bonus event, if one is running."""
        with self.pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM public.events WHERE auto_grant AND is_active "
                "  AND kind = 'grant' AND starts_at <= %s::timestamptz "
                "  AND ends_at > %s::timestamptz "
                "ORDER BY starts_at DESC LIMIT 1",
                (now, now),
            ).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["id"] = str(out["id"])
        return out

    def find_credit_transaction_by_key(
        self, user_id: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        if not _is_uuid(user_id):
            return None
        with self.pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM public.credit_transactions "
                "WHERE user_id = %s AND idempotency_key = %s",
                (user_id, idempotency_key),
            ).fetchone()
        return _to_credit_row(row) if row else None

    def list_credit_transactions(
        self,
        user_id: str,
        *,
        limit: int,
        cursor: str | None = None,
        reason: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not _is_uuid(user_id):
            return [], None

        where = ["user_id = %s"]
        parameters: list[Any] = [user_id]

        if reason:
            where.append("reason = %s")
            parameters.append(reason)

        if cursor:
            created_at, row_id = decode_cursor(cursor)
            where.append(
                "(created_at < %s::timestamptz "
                " OR (created_at = %s::timestamptz AND id < %s::uuid))"
            )
            parameters.extend([created_at, created_at, row_id])

        parameters.append(limit + 1)
        with self.pool.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM public.credit_transactions WHERE "
                + " AND ".join(where)
                + " ORDER BY created_at DESC, id DESC LIMIT %s",
                tuple(parameters),
            ).fetchall()

        items = [_to_credit_row(row) for row in rows]
        next_cursor = None
        if len(items) > limit:
            items = items[:limit]
            next_cursor = encode_cursor(items[-1]["created_at"], items[-1]["id"])
        return items, next_cursor

    def credit_totals(self, user_id: str) -> tuple[int, int]:
        """Lifetime granted and lifetime spent, both as positive numbers."""
        if not _is_uuid(user_id):
            return 0, 0
        with self.pool.connection() as connection:
            row = connection.execute(
                "SELECT "
                "  COALESCE(SUM(delta) FILTER (WHERE delta > 0), 0) AS granted, "
                "  COALESCE(SUM(-delta) FILTER (WHERE delta < 0), 0) AS spent "
                "FROM public.credit_transactions WHERE user_id = %s",
                (user_id,),
            ).fetchone()
        return int(row["granted"]), int(row["spent"])

    def ledger_drift(self) -> list[str]:
        """User ids whose cached balance disagrees with their ledger."""
        with self.pool.connection() as connection:
            rows = connection.execute(
                "SELECT u.id FROM public.users u WHERE u.credit_balance <> COALESCE("
                "  (SELECT SUM(t.delta) FROM public.credit_transactions t "
                "   WHERE t.user_id = u.id), 0)"
            ).fetchall()
        return [str(row["id"]) for row in rows]


def _to_service_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Postgres row onto the shared row-dict contract.

    Timestamps become the same ISO-8601 `Z` strings the SQLite adapter stores,
    so cursors, comparisons, and responses behave identically on either backend.
    """
    normalized: dict[str, Any] = {}
    for column, value in row.items():
        key = DB_TO_SERVICE.get(column, column)
        if isinstance(value, datetime):
            normalized[key] = value.astimezone(UTC).isoformat().replace("+00:00", "Z")
        elif isinstance(value, UUID):
            normalized[key] = str(value)
        else:
            normalized[key] = value
    return normalized


def _to_user(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    user = _to_service_row(row)
    user["id"] = str(user["id"])
    user["is_disabled"] = bool(user["is_disabled"])
    return user


def _is_uuid(value: str) -> bool:
    """Guard the uuid-typed columns.

    Postgres rejects a malformed uuid with a type error, which would surface as
    a 500. A caller passing junk deserves the same 404 as a caller passing a
    well-formed id that does not exist.
    """
    try:
        UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _to_credit_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalise a ledger row onto the same currency the SQLite adapter uses.

    Postgres returns uuid and timestamptz objects; SQLite returns strings, and
    the service layer is written against strings so it never learns which
    database it is talking to.
    """
    out = dict(row)
    for key in ("id", "user_id"):
        if out.get(key) is not None:
            out[key] = str(out[key])
    created = out.get("created_at")
    if created is not None and not isinstance(created, str):
        out["created_at"] = created.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return out


def _payment_like_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalise uuid and timestamptz columns onto the sqlite spelling.

    The service layer is written against strings so it never learns which
    database it is talking to; without this a package id would be a UUID object
    on one backend and a string on the other.
    """
    out = dict(row)
    for key in ("id", "user_id", "package_id"):
        value = out.get(key)
        if value is not None and not isinstance(value, str):
            out[key] = str(value)
    for key in ("created_at", "completed_at"):
        value = out.get(key)
        if value is not None and not isinstance(value, str):
            out[key] = value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return out


def _event_row_pg(row: dict[str, Any]) -> dict[str, Any]:
    """Normalise an event row onto the sqlite spelling."""
    out = dict(row)
    if out.get("id") is not None:
        out["id"] = str(out["id"])
    for key in ("starts_at", "ends_at", "created_at"):
        value = out.get(key)
        if value is not None and not isinstance(value, str):
            out[key] = value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return out
