from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.repository import decode_cursor, encode_cursor, reject_immutable_columns

# The Supabase table spells the owner `user_id` and lives under a different
# name. Adapters own this translation so ProjectService never learns it.
TABLE = "public.video_projects"
SERVICE_TO_DB = {"owner_id": "user_id"}
DB_TO_SERVICE = {value: key for key, value in SERVICE_TO_DB.items()}

SELECTED_COLUMNS = (
    "id, user_id, title, prompt, image_path, provider, status, provider_job_id, "
    "error_code, error_message, duration_seconds, aspect_ratio, video_path, "
    "thumbnail_path, poll_count, attempt_count, idempotency_key, created_at, "
    "updated_at, completed_at"
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
                "supabase/002_add_error_code.sql and "
                "supabase/003_add_fastapi_parity_columns.sql."
            ) from exc

    def close(self) -> None:
        self.pool.close()

    # --- users ---------------------------------------------------------------

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        if not _is_uuid(user_id):
            return None
        with self.pool.connection() as connection:
            row = connection.execute(
                "SELECT u.id, u.email, u.is_disabled, r.name AS role "
                "FROM public.users u JOIN public.roles r ON r.id = u.role_id "
                "WHERE u.id = %s",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "email": row["email"],
            "role": row["role"],
            "is_disabled": bool(row["is_disabled"]),
        }

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
