from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any

from app.repository import (
    UsernameTakenError,
    build_stats,
    decode_cursor,
    encode_cursor,
    reject_immutable_columns,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT,
    username TEXT UNIQUE,
    role TEXT NOT NULL DEFAULT 'user',
    is_disabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z'
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    title TEXT NOT NULL,
    prompt TEXT,
    image_path TEXT,
    provider TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'generating', 'completed', 'failed')),
    provider_job_id TEXT,
    error_code TEXT,
    error_message TEXT,
    duration_seconds INTEGER,
    aspect_ratio TEXT NOT NULL,
    video_path TEXT,
    thumbnail_path TEXT,
    poll_count INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT,
    started_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    deleted_at TEXT,
    UNIQUE(owner_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS projects_owner_created_idx
ON projects(owner_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS projects_status_idx
ON projects(status, updated_at);

CREATE TABLE IF NOT EXISTS generation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    request_id TEXT,
    event TEXT NOT NULL
        CHECK (event IN ('submit', 'poll', 'webhook', 'download', 'error')),
    request TEXT,
    response TEXT,
    http_status INTEGER,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS logs_project_created_idx
ON generation_logs(project_id, created_at DESC);
"""

# Columns added after the first release. SQLite has no `ADD COLUMN IF NOT
# EXISTS`, so an existing database file is widened here rather than recreated;
# dropping the file would lose the local demo history.
ADDED_COLUMNS = {
    "projects": {
        "attempt_count": "INTEGER NOT NULL DEFAULT 0",
        "deleted_at": "TEXT",
        # Nullable: rows written before this column existed fall back to
        # created_at rather than being read as "started at the epoch".
        "started_at": "TEXT",
    },
    "users": {
        "username": "TEXT",
        "created_at": "TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z'",
    },
}


def _as_json(value: Any) -> str | None:
    return None if value is None else json.dumps(value, default=str)


def _from_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:  # pragma: no cover - we wrote it, it parses
        return None


class Database:
    """SQLite adapter: the credential-free local profile (ADR-008)."""

    backend = "sqlite"

    def __init__(self, path: Path) -> None:
        self.path = path
        self._init_lock = Lock()
        self._initialized = False

    def initialize(self) -> None:
        with self._init_lock:
            if self._initialized:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as connection:
                connection.executescript(SCHEMA)
                self._add_missing_columns(connection)
            self._initialized = True

    @staticmethod
    def _add_missing_columns(connection: sqlite3.Connection) -> None:
        for table, columns in ADDED_COLUMNS.items():
            existing = {
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for column, definition in columns.items():
                if column not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # --- users ---------------------------------------------------------------

    def upsert_user(
        self,
        user_id: str,
        *,
        email: str | None = None,
        username: str | None = None,
        role: str = "user",
        is_disabled: bool = False,
        created_at: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO users (id, email, username, role, is_disabled, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET email = excluded.email, "
                "username = excluded.username, role = excluded.role, "
                "is_disabled = excluded.is_disabled",
                (
                    user_id,
                    email,
                    username,
                    role,
                    1 if is_disabled else 0,
                    created_at or "1970-01-01T00:00:00Z",
                ),
            )

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, email, username, role, is_disabled, created_at "
                "FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return self._user_row(row)

    def set_username(self, user_id: str, username: str | None) -> dict[str, Any] | None:
        """Rename, letting the unique index decide.

        Checking availability before writing would still race; translating the
        violation is the only correct version.
        """
        try:
            with self.connect() as connection:
                cursor = connection.execute(
                    "UPDATE users SET username = ? WHERE id = ?",
                    (username, user_id),
                )
                if cursor.rowcount == 0:
                    return None
        except sqlite3.IntegrityError as exc:
            raise UsernameTakenError(username) from exc
        return self.get_user(user_id)

    def list_users(
        self,
        *,
        limit: int,
        cursor: str | None,
        query: str | None,
        role: str | None,
        is_disabled: bool | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        where: list[str] = ["1 = 1"]
        parameters: list[Any] = []

        if query:
            where.append("(lower(email) LIKE ? OR lower(username) LIKE ?)")
            pattern = f"%{query.lower()}%"
            parameters.extend([pattern, pattern])
        if role:
            where.append("role = ?")
            parameters.append(role)
        if is_disabled is not None:
            where.append("is_disabled = ?")
            parameters.append(1 if is_disabled else 0)
        if cursor:
            created_at, user_id = decode_cursor(cursor)
            where.append("(created_at < ? OR (created_at = ? AND id < ?))")
            parameters.extend([created_at, created_at, user_id])

        parameters.append(limit + 1)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT u.id, u.email, u.username, u.role, u.is_disabled, u.created_at, "
                "(SELECT COUNT(*) FROM projects p "
                " WHERE p.owner_id = u.id AND p.deleted_at IS NULL) AS project_count "
                "FROM users u WHERE " + " AND ".join(where) + " "
                "ORDER BY u.created_at DESC, u.id DESC LIMIT ?",
                tuple(parameters),
            ).fetchall()

        users = [self._user_row(row) for row in rows]
        items = [user for user in users[:limit] if user]
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
        assignments: list[str] = []
        parameters: list[Any] = []
        if role is not None:
            assignments.append("role = ?")
            parameters.append(role)
        if is_disabled is not None:
            assignments.append("is_disabled = ?")
            parameters.append(1 if is_disabled else 0)
        if not assignments:
            return self.get_user(user_id)

        parameters.append(user_id)
        with self.connect() as connection:
            cursor = connection.execute(
                f"UPDATE users SET {', '.join(assignments)} WHERE id = ?",
                tuple(parameters),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_user(user_id)

    def count_enabled_admins(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM users "
                "WHERE role = 'admin' AND is_disabled = 0"
            ).fetchone()
        return int(row["total"] or 0)

    def admin_stats(self, since: str) -> dict[str, Any]:
        with self.connect() as connection:
            totals = connection.execute(
                "SELECT (SELECT COUNT(*) FROM users) AS users, "
                "(SELECT COUNT(*) FROM users WHERE is_disabled = 0) AS active_users, "
                "(SELECT COUNT(*) FROM projects WHERE deleted_at IS NULL) AS projects"
            ).fetchone()
            by_status = connection.execute(
                "SELECT status, COUNT(*) AS total FROM projects "
                "WHERE deleted_at IS NULL GROUP BY status"
            ).fetchall()
            by_provider = connection.execute(
                "SELECT provider, COUNT(*) AS total FROM projects "
                "WHERE deleted_at IS NULL GROUP BY provider"
            ).fetchall()
            daily = connection.execute(
                "SELECT substr(created_at, 1, 10) AS date, COUNT(*) AS created, "
                "SUM(status = 'completed') AS completed, "
                "SUM(status = 'failed') AS failed "
                "FROM projects WHERE deleted_at IS NULL AND created_at >= ? "
                "GROUP BY 1 ORDER BY 1 DESC",
                (since,),
            ).fetchall()

        return build_stats(dict(totals), by_status, by_provider, daily)

    @staticmethod
    def _user_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        user = dict(row)
        user["is_disabled"] = bool(user["is_disabled"])
        return user

    # --- projects ------------------------------------------------------------

    def create_project(self, values: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        try:
            with self.connect() as connection:
                connection.execute(
                    f"INSERT INTO projects ({columns}) VALUES ({placeholders})",
                    tuple(values.values()),
                )
                row = connection.execute(
                    "SELECT * FROM projects WHERE id = ?",
                    (values["id"],),
                ).fetchone()
        except sqlite3.IntegrityError:
            key = values.get("idempotency_key")
            if not key:
                raise
            existing = self.find_by_idempotency(values["owner_id"], key)
            if existing is None:
                raise
            return existing, False

        if row is None:  # pragma: no cover - SQLite guarantees RETURN visibility
            raise RuntimeError("Inserted project could not be read back.")
        return dict(row), True

    def find_by_idempotency(self, owner_id: str, key: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects "
                "WHERE owner_id = ? AND idempotency_key = ? AND deleted_at IS NULL",
                (owner_id, key),
            ).fetchone()
        return dict(row) if row else None

    def get_project(self, project_id: str, owner_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects "
                "WHERE id = ? AND owner_id = ? AND deleted_at IS NULL",
                (project_id, owner_id),
            ).fetchone()
        return dict(row) if row else None

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

        assignments = ", ".join(f"{column} = ?" for column in values)
        parameters: list[Any] = [*values.values(), project_id, owner_id]
        status_clause = ""
        if expected_status is not None:
            status_clause = " AND status = ?"
            parameters.append(expected_status)

        with self.connect() as connection:
            cursor = connection.execute(
                f"UPDATE projects SET {assignments} "
                f"WHERE id = ? AND owner_id = ? AND deleted_at IS NULL{status_clause}",
                tuple(parameters),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ? AND owner_id = ?",
                (project_id, owner_id),
            ).fetchone()
        return dict(row) if row else None

    def list_projects(
        self,
        owner_id: str,
        *,
        limit: int,
        status: str | None,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        where = ["owner_id = ?", "deleted_at IS NULL"]
        parameters: list[Any] = [owner_id]

        if status:
            where.append("status = ?")
            parameters.append(status)

        if cursor:
            created_at, project_id = decode_cursor(cursor)
            where.append("(created_at < ? OR (created_at = ? AND id < ?))")
            parameters.extend([created_at, created_at, project_id])

        parameters.append(limit + 1)
        query = (
            "SELECT * FROM projects WHERE "
            + " AND ".join(where)
            + " ORDER BY created_at DESC, id DESC LIMIT ?"
        )
        with self.connect() as connection:
            rows = [dict(row) for row in connection.execute(query, tuple(parameters)).fetchall()]

        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(last["created_at"], last["id"])
        return items, next_cursor

    def claim_in_flight_projects(self, limit: int) -> list[dict[str, Any]]:
        """Oldest-updated in-flight projects.

        SQLite is single-writer, so there is no row-level claim to take here.
        The Postgres adapter uses FOR UPDATE SKIP LOCKED instead, which is what
        makes more than one poller safe.
        """
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM projects "
                "WHERE status IN ('pending', 'generating') AND deleted_at IS NULL "
                "ORDER BY updated_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_generation_log(self, values: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO generation_logs "
                "(project_id, provider, request_id, event, request, response, "
                " http_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    values["project_id"],
                    values["provider"],
                    values.get("request_id"),
                    values["event"],
                    _as_json(values.get("request")),
                    _as_json(values.get("response")),
                    values.get("http_status"),
                    values["created_at"],
                ),
            )

    def generation_logs(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM generation_logs WHERE project_id = ? "
                "ORDER BY created_at ASC, id ASC",
                (project_id,),
            ).fetchall()
        entries = []
        for row in rows:
            entry = dict(row)
            entry["request"] = _from_json(entry["request"])
            entry["response"] = _from_json(entry["response"])
            entries.append(entry)
        return entries

    def count_quota_usage(
        self,
        owner_id: str,
        since: str,
        not_charged: tuple[str, ...],
    ) -> tuple[int, str | None]:
        placeholders = ", ".join("?" for _ in not_charged) or "NULL"
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS used, MIN(created_at) AS oldest FROM projects "
                "WHERE owner_id = ? AND created_at >= ? AND deleted_at IS NULL "
                f"AND (error_code IS NULL OR error_code NOT IN ({placeholders}))",
                (owner_id, since, *not_charged),
            ).fetchone()
        return int(row["used"] or 0), row["oldest"]

    def soft_delete_project(self, project_id: str, owner_id: str, deleted_at: str) -> bool:
        """Soft delete, matching the Express reference.

        The row is retained so a provider callback or poller arriving after the
        delete has something to write to instead of failing on a missing id.
        Stored media is a separate concern and is removed eagerly by the caller.
        """
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE projects SET deleted_at = ?, updated_at = ? "
                "WHERE id = ? AND owner_id = ? AND deleted_at IS NULL",
                (deleted_at, deleted_at, project_id, owner_id),
            )
        return cursor.rowcount > 0
