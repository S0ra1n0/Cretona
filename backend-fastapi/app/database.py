from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any

from app.repository import decode_cursor, encode_cursor, reject_immutable_columns

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    is_disabled INTEGER NOT NULL DEFAULT 0
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
"""

# Columns added after the first release. SQLite has no `ADD COLUMN IF NOT
# EXISTS`, so an existing database file is widened here rather than recreated;
# dropping the file would lose the local demo history.
ADDED_COLUMNS = {
    "attempt_count": "INTEGER NOT NULL DEFAULT 0",
    "deleted_at": "TEXT",
}


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
        existing = {
            row["name"] for row in connection.execute("PRAGMA table_info(projects)").fetchall()
        }
        for column, definition in ADDED_COLUMNS.items():
            if column not in existing:
                connection.execute(f"ALTER TABLE projects ADD COLUMN {column} {definition}")

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
        role: str = "user",
        is_disabled: bool = False,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO users (id, email, role, is_disabled) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET email = excluded.email, "
                "role = excluded.role, is_disabled = excluded.is_disabled",
                (user_id, email, role, 1 if is_disabled else 0),
            )

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, email, role, is_disabled FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
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
