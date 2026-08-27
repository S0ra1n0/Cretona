from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any

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

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT,
    username TEXT UNIQUE,
    role TEXT NOT NULL DEFAULT 'user',
    is_disabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    -- Optional profile details. Only the username is required to finish
    -- setup, so both stay nullable and read as "not chosen yet".
    gender TEXT CHECK (gender IN ('male', 'female', 'other')),
    birthday TEXT,
    -- Cache of the credit ledger. Written only in the same transaction as a
    -- credit_transactions row; never set directly.
    credit_balance INTEGER NOT NULL DEFAULT 0 CHECK (credit_balance >= 0)
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
    lease_owner TEXT,
    lease_expires_at TEXT,
    started_at TEXT,
    progress_percent INTEGER NOT NULL DEFAULT 0,
    step_message TEXT,
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

CREATE INDEX IF NOT EXISTS logs_created_idx
ON generation_logs(created_at ASC, id ASC);

CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    details TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS admin_audit_logs_created_idx
ON admin_audit_logs(created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS admin_audit_logs_action_created_idx
ON admin_audit_logs(action, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS admin_audit_logs_actor_created_idx
ON admin_audit_logs(actor_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS projects_provider_job_idx
ON projects(provider, provider_job_id);

CREATE INDEX IF NOT EXISTS projects_deleted_idx
ON projects(deleted_at, owner_id);

-- Credits, events, packages, payments and settings (migration 013).
--
-- The SQLite mirror. Types differ from Postgres by necessity -- no uuid, no
-- timestamptz, no partial-index-with-predicate on older builds -- but every
-- constraint that protects money is reproduced, because the tests run here and
-- a constraint that only exists in production is a constraint nobody tests.

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_packages (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    credits INTEGER NOT NULL CHECK (credits > 0),
    price_vnd INTEGER NOT NULL CHECK (price_vnd >= 0),
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    package_id TEXT NOT NULL,
    amount_vnd INTEGER NOT NULL CHECK (amount_vnd >= 0),
    credits_granted INTEGER NOT NULL CHECK (credits_granted > 0),
    method TEXT NOT NULL DEFAULT 'simulated',
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
    idempotency_key TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_idempotency
ON payments(user_id, idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS payments_user_created_idx
ON payments(user_id, created_at DESC, id DESC);

-- Minutes are LOCAL Vietnam time (UTC+7) from midnight: 1200 = 20:00.
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('grant', 'discount')),
    bonus_credits INTEGER CHECK (bonus_credits > 0),
    discount_percent INTEGER CHECK (discount_percent BETWEEN 1 AND 100),
    recurrence TEXT NOT NULL CHECK (recurrence IN ('once', 'daily', 'weekly')),
    active_days TEXT,
    active_from_minute INTEGER CHECK (active_from_minute BETWEEN 0 AND 1440),
    active_to_minute INTEGER CHECK (active_to_minute BETWEEN 0 AND 1440),
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    max_claims INTEGER CHECK (max_claims > 0),
    auto_grant INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    CHECK (ends_at > starts_at),
    CHECK (
        (kind = 'grant' AND bonus_credits IS NOT NULL AND discount_percent IS NULL)
     OR (kind = 'discount' AND discount_percent IS NOT NULL AND bonus_credits IS NULL)
    ),
    CHECK ((active_from_minute IS NULL) = (active_to_minute IS NULL))
);

CREATE INDEX IF NOT EXISTS events_active_window_idx
ON events(is_active, starts_at, ends_at);

-- period_key: '' for once, the local date for daily, the ISO week for weekly.
-- This unique constraint -- not a count-then-insert -- is what stops a
-- double-tap claiming the same weekend gift twice.
CREATE TABLE IF NOT EXISTS event_claims (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    period_key TEXT NOT NULL DEFAULT '',
    credits_granted INTEGER NOT NULL CHECK (credits_granted > 0),
    created_at TEXT NOT NULL,
    UNIQUE(event_id, user_id, period_key)
);

CREATE INDEX IF NOT EXISTS event_claims_event_created_idx
ON event_claims(event_id, created_at DESC);

CREATE INDEX IF NOT EXISTS event_claims_user_created_idx
ON event_claims(user_id, created_at DESC);

-- The append-only ledger. users.credit_balance is a cache; this is the truth.
-- balance_after exists so drift between the two is a query, not a surprise.
CREATE TABLE IF NOT EXISTS credit_transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    delta INTEGER NOT NULL CHECK (delta <> 0),
    balance_after INTEGER NOT NULL CHECK (balance_after >= 0),
    reason TEXT NOT NULL CHECK (reason IN (
        'signup_bonus', 'event_grant', 'purchase',
        'generation', 'refund', 'admin_adjustment')),
    ref_type TEXT CHECK (ref_type IN ('project', 'payment', 'event')),
    ref_id TEXT,
    note TEXT,
    idempotency_key TEXT,
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_tx_idempotency
ON credit_transactions(user_id, idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS credit_tx_user_created_idx
ON credit_transactions(user_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS credit_tx_reason_created_idx
ON credit_transactions(reason, created_at DESC);

CREATE INDEX IF NOT EXISTS credit_tx_ref_idx
ON credit_transactions(ref_type, ref_id);

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
        "lease_owner": "TEXT",
        "lease_expires_at": "TEXT",
        "progress_percent": "INTEGER NOT NULL DEFAULT 0",
        "step_message": "TEXT",
    },
    "users": {
        "username": "TEXT",
        "created_at": "TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z'",
        # Storage object key for the profile avatar, never a signed URL
        # (supabase/010_add_user_avatar.sql).
        "avatar_path": "TEXT",
        # Optional profile details (supabase/012_add_user_profile_fields.sql).
        # No CHECK constraint here: SQLite cannot add one via ALTER TABLE, so
        # the value is validated by the MeUpdate schema before it ever lands.
        "gender": "TEXT",
        "birthday": "TEXT",
        # Credit balance cache (supabase/013_add_credits_and_events.sql). No
        # CHECK here for the same reason as gender: SQLite cannot add one via
        # ALTER TABLE. CreditService is the only writer and refuses to go
        # negative, and the fresh-database SCHEMA above does carry the check.
        "credit_balance": "INTEGER NOT NULL DEFAULT 0",
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
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = NORMAL")
                connection.execute("PRAGMA cache_size = -64000")
                connection.execute("PRAGMA mmap_size = 268435456")
                connection.executescript(SCHEMA)
                self._add_missing_columns(connection)
                self._seed_defaults(connection)
            self._initialized = True

    @staticmethod
    def _seed_defaults(connection: sqlite3.Connection) -> None:
        """Mirror supabase/seed_credits_and_events.sql into the local database.

        Postgres gets these from a seed script run against Supabase. Nothing
        runs that script against the sqlite mirror, so a local or test database
        had the tables but no rows -- which meant no generation cost, no signup
        bonus, and a new account that could never generate anything.

        Only the rows the product cannot start without: the cost setting and
        the signup bonus. Packages, hot hours and the rest are campaign data,
        and inventing them here would put a second source of truth next to the
        SQL. Guarded, so a row an operator changed is never overwritten.
        """
        connection.execute(
            "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            ("generation_cost_credits", "1", "1970-01-01T00:00:00Z"),
        )
        # Mirrors supabase/seed_credits_and_events.sql. That file is the
        # source of truth for prices; these exist so a local demo has something
        # to buy rather than an empty screen. `test_sqlite_defaults_match_the_seed`
        # fails if the two drift apart.
        for package_id, name, credits, price, order in (
            ("00000000-0000-4000-8000-00000000p001", "Starter", 10, 20000, 1),
            ("00000000-0000-4000-8000-00000000p002", "Creator", 50, 90000, 2),
            ("00000000-0000-4000-8000-00000000p003", "Studio", 150, 250000, 3),
        ):
            connection.execute(
                "INSERT OR IGNORE INTO credit_packages "
                "(id, name, credits, price_vnd, sort_order, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (package_id, name, credits, price, order, "1970-01-01T00:00:00Z"),
            )
        connection.execute(
            "INSERT OR IGNORE INTO events "
            "(id, code, name, description, kind, bonus_credits, recurrence, "
            " starts_at, ends_at, auto_grant, is_active, created_at) "
            "VALUES (?, ?, ?, ?, 'grant', 5, 'once', ?, ?, 1, 1, ?)",
            (
                "00000000-0000-4000-8000-00000000e001",
                "SIGNUP_BONUS",
                "Welcome bonus",
                "Five credits to get you started, added when you first sign in.",
                "1970-01-01T00:00:00Z",
                "2099-01-01T00:00:00Z",
                "1970-01-01T00:00:00Z",
            ),
        )

    @staticmethod
    def _add_missing_columns(connection: sqlite3.Connection) -> None:
        for table, columns in ADDED_COLUMNS.items():
            existing = {
                row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
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
        connection.execute("PRAGMA synchronous = NORMAL")
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
                "SELECT id, email, username, avatar_path, gender, birthday, "
                "role, is_disabled, created_at "
                "FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return self._user_row(row)

    def sync_user_email(self, user_id: str, email: str) -> None:
        """Record the email a verified token claims for this account.

        Rows are created by the Supabase signup trigger, which is the only
        thing that has ever written `users.email`; nothing refreshed it
        afterwards, so a changed address never reached this database and the
        profile screen kept showing whatever the row was seeded with. Written
        only when it actually differs, so the common request does no write.
        """
        with self.connect() as connection:
            connection.execute(
                "UPDATE users SET email = ? WHERE id = ? AND (email IS NULL OR email <> ?)",
                (email, user_id, email),
            )

    def set_username(self, user_id: str, username: str | None) -> dict[str, Any] | None:
        """Rename, letting the unique index decide.

        Checking availability before writing would still race; translating the
        violation is the only correct version.
        """
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
        assignments = ["username = ?"]
        parameters: list[Any] = [username]
        if set_avatar:
            assignments.append("avatar_path = ?")
            parameters.append(avatar_path)
        if set_gender:
            assignments.append("gender = ?")
            parameters.append(gender)
        if set_birthday:
            assignments.append("birthday = ?")
            parameters.append(birthday)
        parameters.append(user_id)

        try:
            with self.connect() as connection:
                cursor = connection.execute(
                    f"UPDATE users SET {', '.join(assignments)} WHERE id = ?",
                    tuple(parameters),
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
        audit: AuditEntry | None = None,
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
            # One transaction, so a privilege change cannot commit without its
            # audit row and an unwritable audit table cannot let one through
            # unrecorded (T2-5).
            cursor = connection.execute(
                f"UPDATE users SET {', '.join(assignments)} WHERE id = ?",
                tuple(parameters),
            )
            if cursor.rowcount == 0:
                return None
            if audit is not None:
                self._insert_audit_log(connection, audit)
        return self.get_user(user_id)

    def count_enabled_admins(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM users WHERE role = 'admin' AND is_disabled = 0"
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
                "SELECT * FROM projects WHERE id = ? AND owner_id = ? AND deleted_at IS NULL",
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

    def get_project_by_id(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
        return dict(row) if row else None

    def find_by_provider_job_id(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE provider_job_id = ? AND deleted_at IS NULL",
                (job_id,),
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

    def claim_in_flight_projects(
        self,
        limit: int,
        *,
        owner: str,
        now: str,
        lease_until: str,
        providers: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Take a durable lease on a batch of in-flight projects.

        The claim is written to the row rather than held as a lock, because the
        work that follows is HTTP calls to a provider and must not run inside an
        open transaction. A lock would be released the moment this returns.

        `providers` scopes the claim (W1). Two claimants poll this table -- the
        in-process poller and an external worker -- and without a filter they
        race for the same rows. The loser waits, so a job is served late or by a
        machine that cannot run it. Passing disjoint sets makes that structural
        rather than a matter of timing. None means "any", which is what the
        admin backfill and the tests want.
        """
        provider_filter = ""
        provider_args: tuple[str, ...] = ()
        if providers is not None:
            if not providers:
                # An empty set is not "no filter". A caller that can run nothing
                # must claim nothing, or it would silently claim everything.
                return []
            placeholders = ", ".join("?" for _ in providers)
            provider_filter = f"  AND provider IN ({placeholders}) "
            provider_args = tuple(providers)

        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id FROM projects "
                "WHERE status IN ('pending', 'generating') AND deleted_at IS NULL "
                "  AND (lease_expires_at IS NULL OR lease_expires_at < ?) "
                f"{provider_filter}"
                "ORDER BY updated_at ASC LIMIT ?",
                (now, *provider_args, limit),
            ).fetchall()
            claimed = [row["id"] for row in rows]
            if not claimed:
                return []

            placeholders = ", ".join("?" for _ in claimed)
            connection.execute(
                f"UPDATE projects SET lease_owner = ?, lease_expires_at = ? "
                f"WHERE id IN ({placeholders})",
                (owner, lease_until, *claimed),
            )
            leased = connection.execute(
                f"SELECT * FROM projects WHERE id IN ({placeholders})",
                tuple(claimed),
            ).fetchall()
        return [dict(row) for row in leased]

    def release_lease(self, project_id: str, owner: str) -> None:
        """Give the row back, so the next pass can pick it up immediately.

        Scoped to the owner: a poller whose lease already expired and was taken
        by someone else must not clear the new holder's claim.
        """
        with self.connect() as connection:
            connection.execute(
                "UPDATE projects SET lease_owner = NULL, lease_expires_at = NULL "
                "WHERE id = ? AND lease_owner = ?",
                (project_id, owner),
            )

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

    # --- credits -------------------------------------------------------------

    def get_setting(self, key: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str, *, updated_by: str, updated_at: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO settings (key, value, updated_by, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
                (key, value, updated_by, updated_at),
            )

    def get_credit_balance(self, user_id: str) -> int | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT credit_balance FROM users WHERE id = ?", (user_id,)
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
    ) -> tuple[dict[str, Any], bool]:
        """Move a balance and write its ledger row, atomically.

        One method rather than two calls, because the balance and the ledger
        must move together or not at all. A service that updated the balance
        and then inserted the row would leave money unexplained whenever the
        second statement failed.

        Returns `(row, created)`. `created` is False when `idempotency_key` had
        already been used, in which case the original row comes back and
        nothing moved -- that is what makes a retried submit safe.
        """
        try:
            with self.connect() as connection:
                # IMMEDIATE takes the write lock up front. Without it two
                # concurrent charges can both read the same balance before
                # either writes, and the second overwrites the first.
                connection.execute("BEGIN IMMEDIATE")
                updated = connection.execute(
                    "UPDATE users SET credit_balance = credit_balance + ? "
                    "WHERE id = ? AND credit_balance + ? >= 0 "
                    "RETURNING credit_balance",
                    (delta, user_id, delta),
                ).fetchone()
                if updated is None:
                    # Either the user does not exist or the charge would go
                    # negative. Distinguishing them costs a second query and
                    # the caller treats both as "cannot charge".
                    exists = connection.execute(
                        "SELECT 1 FROM users WHERE id = ?", (user_id,)
                    ).fetchone()
                    raise (
                        InsufficientCreditsError(user_id)
                        if exists
                        else UnknownUserError(user_id)
                    )

                balance_after = int(updated["credit_balance"])
                connection.execute(
                    "INSERT INTO credit_transactions "
                    "(id, user_id, delta, balance_after, reason, ref_type, ref_id, "
                    " note, idempotency_key, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        transaction_id, user_id, delta, balance_after, reason,
                        ref_type, ref_id, note, idempotency_key, created_at,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM credit_transactions WHERE id = ?", (transaction_id,)
                ).fetchone()
        except sqlite3.IntegrityError:
            if not idempotency_key:
                raise
            existing = self.find_credit_transaction_by_key(user_id, idempotency_key)
            if existing is None:
                raise
            return existing, False

        if row is None:  # pragma: no cover - just inserted
            raise RuntimeError("Inserted credit transaction could not be read back.")
        return dict(row), True

    # --- packages and payments -----------------------------------------------

    def list_credit_packages(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM credit_packages"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY sort_order ASC, credits ASC"
        with self.connect() as connection:
            rows = connection.execute(query).fetchall()
        return [_package_row(dict(row)) for row in rows]

    def get_credit_package(self, package_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM credit_packages WHERE id = ?", (package_id,)
            ).fetchone()
        return _package_row(dict(row)) if row else None

    def find_payment_by_key(
        self, user_id: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM payments WHERE user_id = ? AND idempotency_key = ?",
                (user_id, idempotency_key),
            ).fetchone()
        return dict(row) if row else None

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

        Contract §8.2. A payment that completed without granting credits, or
        credits granted with no payment behind them, are both states no
        reconciliation could untangle -- so neither is reachable.

        Returns `(payment, created)`; `created` is False when the idempotency
        key had already been used, and nothing moved.
        """
        try:
            with self.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                updated = connection.execute(
                    "UPDATE users SET credit_balance = credit_balance + ? "
                    "WHERE id = ? RETURNING credit_balance",
                    (credits_granted, user_id),
                ).fetchone()
                if updated is None:
                    raise UnknownUserError(user_id)

                connection.execute(
                    "INSERT INTO payments (id, user_id, package_id, amount_vnd, "
                    " credits_granted, method, status, idempotency_key, created_at, "
                    " completed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?)",
                    (
                        payment_id, user_id, package_id, amount_vnd, credits_granted,
                        method, idempotency_key, created_at, created_at,
                    ),
                )
                connection.execute(
                    "INSERT INTO credit_transactions "
                    "(id, user_id, delta, balance_after, reason, ref_type, ref_id, "
                    " note, idempotency_key, created_at) "
                    "VALUES (?, ?, ?, ?, 'purchase', 'payment', ?, ?, ?, ?)",
                    (
                        transaction_id, user_id, credits_granted,
                        int(updated["credit_balance"]), payment_id, None,
                        f"purchase:{payment_id}", created_at,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM payments WHERE id = ?", (payment_id,)
                ).fetchone()
        except sqlite3.IntegrityError:
            if not idempotency_key:
                raise
            existing = self.find_payment_by_key(user_id, idempotency_key)
            if existing is None:
                raise
            return existing, False

        if row is None:  # pragma: no cover - just inserted
            raise RuntimeError("Inserted payment could not be read back.")
        return dict(row), True

    def find_auto_grant_event(self, now: str) -> dict[str, Any] | None:
        """The active signup-bonus event, if one is running.

        `auto_grant` events have no button: they apply the first time an
        account is seen. Only one is expected at a time; the newest wins if a
        campaign was replaced without the old one being deactivated.
        """
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM events WHERE auto_grant = 1 AND is_active = 1 "
                "  AND kind = 'grant' AND starts_at <= ? AND ends_at > ? "
                "ORDER BY starts_at DESC LIMIT 1",
                (now, now),
            ).fetchone()
        return dict(row) if row else None

    def find_credit_transaction_by_key(
        self, user_id: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM credit_transactions "
                "WHERE user_id = ? AND idempotency_key = ?",
                (user_id, idempotency_key),
            ).fetchone()
        return dict(row) if row else None

    def list_credit_transactions(
        self,
        user_id: str,
        *,
        limit: int,
        cursor: str | None = None,
        reason: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        where = ["user_id = ?"]
        parameters: list[Any] = [user_id]

        if reason:
            where.append("reason = ?")
            parameters.append(reason)

        if cursor:
            created_at, row_id = decode_cursor(cursor)
            where.append("(created_at < ? OR (created_at = ? AND id < ?))")
            parameters.extend([created_at, created_at, row_id])

        parameters.append(limit + 1)
        rows = []
        with self.connect() as connection:
            rows = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM credit_transactions WHERE "
                    + " AND ".join(where)
                    + " ORDER BY created_at DESC, id DESC LIMIT ?",
                    tuple(parameters),
                ).fetchall()
            ]

        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = encode_cursor(rows[-1]["created_at"], rows[-1]["id"])
        return rows, next_cursor

    def credit_totals(self, user_id: str) -> tuple[int, int]:
        """Lifetime granted and lifetime spent, both as positive numbers."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT "
                "  COALESCE(SUM(CASE WHEN delta > 0 THEN delta END), 0) AS granted, "
                "  COALESCE(SUM(CASE WHEN delta < 0 THEN -delta END), 0) AS spent "
                "FROM credit_transactions WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return int(row["granted"]), int(row["spent"])

    def ledger_drift(self) -> list[str]:
        """User ids whose cached balance disagrees with their ledger.

        `balance_after` and this query are the reason the cache is safe to
        keep: drift is detectable by asking, rather than by a user noticing
        their credits are wrong.
        """
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT u.id FROM users u WHERE u.credit_balance <> COALESCE("
                "  (SELECT SUM(t.delta) FROM credit_transactions t WHERE t.user_id = u.id), 0)"
            ).fetchall()
        return [row["id"] for row in rows]

    def list_projects_missing_thumbnails(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM projects "
                "WHERE status = 'completed' AND video_path IS NOT NULL "
                "AND (thumbnail_path IS NULL OR thumbnail_path = '') "
                "AND deleted_at IS NULL"
            ).fetchall()
        return [dict(row) for row in rows]

    def prune_generation_logs(self, before: str, limit: int) -> list[dict[str, Any]]:
        """Atomically delete one oldest-first batch and return metadata only.

        The provider payload columns are deliberately not returned. Retention
        summaries must never become a second, longer-lived copy of prompts or
        provider responses.
        """
        with self.connect() as connection:
            rows = connection.execute(
                "DELETE FROM generation_logs WHERE id IN ("
                "SELECT id FROM generation_logs WHERE created_at < ? "
                "ORDER BY created_at ASC, id ASC LIMIT ?"
                ") RETURNING provider, event, http_status",
                (before, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_quota_usage(
        self,
        owner_id: str,
        since: str,
        not_charged: tuple[str, ...],
    ) -> tuple[int, str | None]:
        placeholders = ", ".join("?" for _ in not_charged) or "NULL"
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE("
                "SUM(CASE WHEN provider IN ('real', 'wan21', 'cloud', 'local') "
                "OR duration_seconds > 5 THEN 2 ELSE 1 END), "
                "0) AS used, "
                "MIN(created_at) AS oldest FROM projects "
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

    @staticmethod
    def _insert_audit_log(connection: sqlite3.Connection, entry: AuditEntry) -> None:
        """The INSERT alone, on a caller-supplied connection.

        Kept separate so a mutation can enlist it in its own transaction rather
        than opening a second one that commits independently.
        """
        connection.execute(
            "INSERT INTO admin_audit_logs ("
            "id, actor_id, action, target_type, target_id, details, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                entry.id,
                entry.actor_id,
                entry.action,
                entry.target_type,
                entry.target_id,
                _as_json(entry.details) if entry.details is not None else None,
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
        with self.connect() as connection:
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
            clauses.append("action = ?")
            params.append(action)
        if actor_id:
            clauses.append("actor_id = ?")
            params.append(actor_id)
        if cursor:
            cursor_created_at, cursor_id = decode_cursor(cursor)
            clauses.append("(created_at < ? OR (created_at = ? AND id < ?))")
            params.extend([cursor_created_at, cursor_created_at, cursor_id])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            f"SELECT * FROM admin_audit_logs {where_sql} ORDER BY created_at DESC, id DESC LIMIT ?"
        )
        params.append(limit + 1)
        with self.connect() as connection:
            rows = [dict(row) for row in connection.execute(query, tuple(params)).fetchall()]

        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = encode_cursor(last["created_at"], last["id"])

        for row in rows:
            if row.get("details"):
                row["details"] = _from_json(row["details"])

        return rows, next_cursor


def _package_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalise sqlite's integer booleans onto real ones."""
    row["is_active"] = bool(row["is_active"])
    return row
