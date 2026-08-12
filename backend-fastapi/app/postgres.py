from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from app.repository import (
    UsernameTakenError,
    build_stats,
    decode_cursor,
    encode_cursor,
    reject_immutable_columns,
)

USER_COLUMNS = (
    "u.id, u.email, u.username, u.is_disabled, u.created_at, r.name AS role"
)

# The Supabase table spells the owner `user_id` and lives under a different
# name. Adapters own this translation so ProjectService never learns it.
TABLE = "public.video_projects"
SERVICE_TO_DB = {"owner_id": "user_id"}
DB_TO_SERVICE = {value: key for key, value in SERVICE_TO_DB.items()}

SELECTED_COLUMNS = (
    "id, user_id, title, prompt, image_path, provider, status, provider_job_id, "
    "error_code, error_message, duration_seconds, aspect_ratio, video_path, "
    "thumbnail_path, poll_count, attempt_count, idempotency_key, started_at, "
    "created_at, updated_at, completed_at"
)


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
                connection.execute(f"SELECT {SELECTED_COLUMNS} FROM {TABLE} LIMIT 0")
        except psycopg.errors.UndefinedTable as exc:
            raise SchemaMismatchError(
                f"{TABLE} is missing. Apply supabase/bootstrap.sql first."
            ) from exc
        except psycopg.errors.UndefinedColumn as exc:
            raise SchemaMismatchError(
                f"{TABLE} is missing a column this backend needs. Apply "
                "supabase/002_add_error_code.sql, "
                "supabase/003_add_fastapi_parity_columns.sql, and "
                "supabase/004_add_started_at.sql."
            ) from exc

    def close(self) -> None:
        self.pool.close()

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

    def set_username(self, user_id: str, username: str | None) -> dict[str, Any] | None:
        if not _is_uuid(user_id):
            return None
        try:
            with self.pool.connection() as connection:
                changed = connection.execute(
                    "UPDATE public.users SET username = %s WHERE id = %s",
                    (username, user_id),
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
        with self.pool.connection() as connection:
            changed = connection.execute(
                f"UPDATE public.users SET {', '.join(assignments)} WHERE id = %s",
                tuple(parameters),
            ).rowcount
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
                "(created_at < %s::timestamptz "
                "OR (created_at = %s::timestamptz AND id < %s::uuid))"
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

    def claim_in_flight_projects(self, limit: int) -> list[dict[str, Any]]:
        """Claim a batch, skipping rows another poller already holds.

        FOR UPDATE SKIP LOCKED is what makes running more than one instance
        safe: two pollers take disjoint batches instead of both advancing the
        same project and double-submitting it to the provider.
        """
        with self.pool.connection() as connection:
            rows = connection.execute(
                f"SELECT {SELECTED_COLUMNS} FROM {TABLE} "
                "WHERE status IN ('pending', 'generating') AND deleted_at IS NULL "
                "ORDER BY updated_at ASC LIMIT %s FOR UPDATE SKIP LOCKED",
                (limit,),
            ).fetchall()
        return [_to_service_row(row) for row in rows]

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

    def count_quota_usage(
        self,
        owner_id: str,
        since: str,
        not_charged: tuple[str, ...],
    ) -> tuple[int, str | None]:
        with self.pool.connection() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS used, MIN(created_at) AS oldest FROM {TABLE} "
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
