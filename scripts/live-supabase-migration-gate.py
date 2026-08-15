"""Guarded preflight, apply, and verification for Cretona migrations 006-008.

Run this script only with the repository's pinned FastAPI virtual environment.
It reads the ignored root ``env`` file, validates that SUPABASE_URL and
DIRECT_URL identify the same project, and never emits credential values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = ROOT / "env"
MIGRATIONS = {
    "006": (
        ROOT / "supabase" / "006_add_generation_log_retention_index.sql",
        "76ece1e4e7c9361902451d656350a154eeaf9db21a5c56d59543b852a001e401",
    ),
    "007": (
        ROOT / "supabase" / "007_add_shared_rate_limits.sql",
        "c698312bbc36474113b9ae529f57bff6fcfc32241cc87dbf44c45b7d33e14d63",
    ),
    "008": (
        ROOT / "supabase" / "008_add_admin_audit_logs.sql",
        "8568cbe123eb2403752be5d82ee626585fe83a38416b19a00f5d2af4fd369ee7",
    ),
}
DATA_API_ROLES = ("anon", "authenticated", "service_role")


class GateError(RuntimeError):
    """An expected safety gate failed without exposing connection details."""


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def validated_connection(env_file: Path) -> tuple[str, str]:
    if not env_file.is_file():
        raise GateError("Selected env file does not exist.")
    values = parse_env(env_file)
    try:
        supabase_url = values["SUPABASE_URL"]
        direct_url = values["DIRECT_URL"]
    except KeyError as exc:
        raise GateError(f"Required key {exc.args[0]} is missing from the env file.") from None

    project = urlparse(supabase_url)
    if project.scheme != "https" or not (project.hostname or "").endswith(".supabase.co"):
        raise GateError("SUPABASE_URL is not a valid Supabase project URL.")
    project_ref = (project.hostname or "").split(".", 1)[0]

    database = urlparse(direct_url)
    if database.scheme not in {"postgres", "postgresql"} or not database.hostname:
        raise GateError("DIRECT_URL is not a valid PostgreSQL connection string.")
    database_user = unquote(database.username or "")
    host_matches = database.hostname.casefold() == f"db.{project_ref}.supabase.co".casefold()
    pooler_user_matches = database_user.casefold().endswith(f".{project_ref}".casefold())
    if not (host_matches or pooler_user_matches):
        raise GateError("DIRECT_URL does not match the project identity from SUPABASE_URL.")
    return direct_url, project_ref


def migration_sql(number: str) -> str:
    path, expected_hash = MIGRATIONS[number]
    payload = path.read_bytes()
    observed_hash = hashlib.sha256(payload).hexdigest()
    if observed_hash != expected_hash:
        raise GateError(
            f"Migration {number} hash mismatch; refusing to use an unreviewed candidate."
        )
    return payload.decode("utf-8-sig")


def fetch_one(cursor: psycopg.Cursor[Any], query: str, params: tuple[Any, ...] = ()) -> Any:
    cursor.execute(query, params)
    row = cursor.fetchone()
    if row is None:
        raise GateError("Expected one metadata row but received none.")
    return row


def collect_state(cursor: psycopg.Cursor[Any]) -> dict[str, Any]:
    server = fetch_one(
        cursor,
        "select current_setting('server_version') as version, "
        "current_setting('server_version_num')::int as version_num",
    )
    columns = cursor.execute(
        """
        select table_name, column_name, data_type, udt_name, is_nullable
        from information_schema.columns
        where table_schema = 'public'
          and (
            (table_name = 'video_projects' and column_name in
              ('started_at', 'lease_owner', 'lease_expires_at'))
            or table_name in ('rate_limit_hits', 'admin_audit_logs')
          )
        order by table_name, ordinal_position
        """
    ).fetchall()
    indexes = cursor.execute(
        """
        select i.tablename, i.indexname, i.indexdef,
               x.indisvalid, x.indisready, x.indislive
        from pg_indexes i
        join pg_class c on c.relname = i.indexname
        join pg_namespace n on n.oid = c.relnamespace and n.nspname = i.schemaname
        join pg_index x on x.indexrelid = c.oid
        where i.schemaname = 'public'
          and i.indexname in (
            'idx_projects_started_at', 'idx_projects_lease',
            'idx_logs_retention', 'rate_limit_hits_pkey',
            'idx_rate_limit_caller_window', 'idx_rate_limit_cleanup'
          )
        order by i.indexname
        """
    ).fetchall()
    invalid_indexes = cursor.execute(
        """
        select c.relname as index_name
        from pg_index i
        join pg_class c on c.oid = i.indexrelid
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and (not i.indisvalid or not i.indisready or not i.indislive)
        order by c.relname
        """
    ).fetchall()
    table_state = fetch_one(
        cursor,
        """
        select
          to_regclass('public.rate_limit_hits') is not null as rate_limit_table,
          to_regclass('public.admin_audit_logs') is not null as audit_table,
          to_regclass('supabase_migrations.schema_migrations') is not null as cli_history
        """,
    )
    return {
        "server": server,
        "columns": columns,
        "indexes": indexes,
        "invalid_indexes": invalid_indexes,
        "rate_limit_table": table_state["rate_limit_table"],
        "audit_table": table_state["audit_table"],
        "cli_history": table_state["cli_history"],
    }


def index_by_name(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["indexname"]: row for row in state["indexes"]}


def assert_index(
    indexes: dict[str, dict[str, Any]], name: str, required_fragments: tuple[str, ...]
) -> None:
    try:
        index = indexes[name]
    except KeyError:
        raise GateError(f"Required index {name} is absent.") from None
    definition = re.sub(r"\s+", " ", index["indexdef"].casefold())
    if not all(fragment.casefold() in definition for fragment in required_fragments):
        raise GateError(f"Index {name} has an unexpected definition.")
    if not all(index[field] for field in ("indisvalid", "indisready", "indislive")):
        raise GateError(f"Index {name} is not valid, ready, and live.")


def assert_004_005(state: dict[str, Any]) -> None:
    observed = {
        (row["table_name"], row["column_name"]): (row["data_type"], row["udt_name"])
        for row in state["columns"]
    }
    expected = {
        ("video_projects", "started_at"): ("timestamp with time zone", "timestamptz"),
        ("video_projects", "lease_owner"): ("text", "text"),
        ("video_projects", "lease_expires_at"): ("timestamp with time zone", "timestamptz"),
    }
    for key, definition in expected.items():
        if observed.get(key) != definition:
            raise GateError(f"Live baseline mismatch for {key[0]}.{key[1]}.")
    indexes = index_by_name(state)
    assert_index(indexes, "idx_projects_started_at", ("video_projects", "started_at"))
    assert_index(
        indexes,
        "idx_projects_lease",
        (
            "video_projects",
            "lease_expires_at",
            "status",
            "pending",
            "generating",
            "deleted_at is null",
        ),
    )


def assert_006(state: dict[str, Any], *, present: bool) -> None:
    indexes = index_by_name(state)
    if not present:
        if "idx_logs_retention" in indexes:
            raise GateError("MIG-006 is already present; refusing an unplanned re-apply.")
        return
    assert_index(
        indexes,
        "idx_logs_retention",
        ("generation_logs", "created_at", "id"),
    )


def assert_007_absent(state: dict[str, Any]) -> None:
    if state["rate_limit_table"]:
        raise GateError("MIG-007 table is already present; refusing an unplanned re-apply.")
    unexpected = {
        "rate_limit_hits_pkey",
        "idx_rate_limit_caller_window",
        "idx_rate_limit_cleanup",
    }.intersection(index_by_name(state))
    if unexpected:
        raise GateError("MIG-007 indexes exist without the expected table state.")


def assert_008(state: dict[str, Any], *, present: bool) -> None:
    if state["audit_table"] != present:
        raise GateError(
            "public.admin_audit_logs is "
            f"{'absent' if present else 'already present'}; refusing to continue."
        )
    if not present:
        return

    # The columns the backend actually writes, in the shapes it writes them.
    # The first draft of 008 had target_id NOT NULL and details as text, which
    # would have failed every thumbnail backfill and returned JSON as a string.
    audit_columns = {
        row["column_name"]: row
        for row in state["columns"]
        if row["table_name"] == "admin_audit_logs"
    }
    for name in ("id", "actor_id", "action", "target_type", "target_id", "details", "created_at"):
        if name not in audit_columns:
            raise GateError(f"public.admin_audit_logs is missing {name}.")
    if audit_columns["target_id"]["is_nullable"] != "YES":
        raise GateError("admin_audit_logs.target_id must be nullable for system-wide actions.")
    if audit_columns["details"]["udt_name"] != "jsonb":
        raise GateError("admin_audit_logs.details must be jsonb, not text.")


def collect_007_verification(cursor: psycopg.Cursor[Any]) -> dict[str, Any]:
    state = collect_state(cursor)
    columns = [row for row in state["columns"] if row["table_name"] == "rate_limit_hits"]
    expected_columns = [
        ("id", "bigint", "int8", "NO"),
        ("caller_key", "text", "text", "NO"),
        ("bucket", "text", "text", "NO"),
        ("occurred_at", "timestamp with time zone", "timestamptz", "NO"),
    ]
    observed_columns = [
        (row["column_name"], row["data_type"], row["udt_name"], row["is_nullable"])
        for row in columns
    ]
    if observed_columns != expected_columns:
        raise GateError("MIG-007 column contract does not match the pinned migration.")

    indexes = index_by_name(state)
    assert_index(indexes, "rate_limit_hits_pkey", ("rate_limit_hits", "id"))
    assert_index(
        indexes,
        "idx_rate_limit_caller_window",
        ("rate_limit_hits", "caller_key", "bucket", "occurred_at", "id"),
    )
    assert_index(
        indexes,
        "idx_rate_limit_cleanup",
        ("rate_limit_hits", "occurred_at", "id"),
    )

    constraints = cursor.execute(
        """
        select conname, pg_get_constraintdef(oid) as definition
        from pg_constraint
        where conrelid = 'public.rate_limit_hits'::regclass
        order by conname
        """
    ).fetchall()
    constraint_names = {row["conname"] for row in constraints}
    expected_constraint_names = {
        "rate_limit_hits_pkey",
        "chk_rate_limit_caller_key",
        "chk_rate_limit_bucket",
    }
    if constraint_names != expected_constraint_names:
        raise GateError("MIG-007 constraint inventory is unexpected.")

    rls = fetch_one(
        cursor,
        """
        select relrowsecurity, relforcerowsecurity
        from pg_class
        where oid = 'public.rate_limit_hits'::regclass
        """,
    )
    if not rls["relrowsecurity"]:
        raise GateError("RLS is not enabled on public.rate_limit_hits.")

    policies = fetch_one(
        cursor,
        "select count(*)::int as count from pg_policies "
        "where schemaname = 'public' and tablename = 'rate_limit_hits'",
    )["count"]
    if policies != 0:
        raise GateError("The internal rate-limit table unexpectedly has RLS policies.")

    privilege_checks: list[dict[str, Any]] = []
    for role in DATA_API_ROLES:
        for privilege in (
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "TRUNCATE",
            "REFERENCES",
            "TRIGGER",
        ):
            granted = fetch_one(
                cursor,
                "select has_table_privilege(%s, 'public.rate_limit_hits', %s) as granted",
                (role, privilege),
            )["granted"]
            privilege_checks.append(
                {
                    "object": "table",
                    "role": role,
                    "privilege": privilege,
                    "granted": granted,
                }
            )
        for privilege in ("USAGE", "SELECT", "UPDATE"):
            granted = fetch_one(
                cursor,
                "select has_sequence_privilege(%s, 'public.rate_limit_hits_id_seq', %s) as granted",
                (role, privilege),
            )["granted"]
            privilege_checks.append(
                {
                    "object": "sequence",
                    "role": role,
                    "privilege": privilege,
                    "granted": granted,
                }
            )
    if any(check["granted"] for check in privilege_checks):
        raise GateError("A Data API role retains privileges on MIG-007 objects.")

    row_estimate = fetch_one(
        cursor,
        "select reltuples::bigint as estimated_rows from pg_class "
        "where oid = 'public.rate_limit_hits'::regclass",
    )["estimated_rows"]
    return {
        "state": state,
        "constraints": constraints,
        "rls": rls,
        "policy_count": policies,
        "data_api_privilege_checks": privilege_checks,
        "estimated_rows": row_estimate,
    }


def read_only_state(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    with (
        connection.transaction(),
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        cursor.execute("set transaction read only")
        cursor.execute("set local statement_timeout = '10s'")
        cursor.execute("set local lock_timeout = '2s'")
        read_only = fetch_one(cursor, "show transaction_read_only")["transaction_read_only"]
        if read_only != "on":
            raise GateError("Read-only transaction guard did not activate.")
        state = collect_state(cursor)
    state["transaction_read_only"] = read_only
    return state


def run_preflight(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    state = read_only_state(connection)
    assert_004_005(state)
    assert_006(state, present=False)
    assert_007_absent(state)
    if state["invalid_indexes"]:
        raise GateError("The public schema contains an invalid, unready, or non-live index.")
    return state


def run_apply(connection: psycopg.Connection[Any], number: str) -> dict[str, Any]:
    state = read_only_state(connection)
    assert_004_005(state)
    if number == "006":
        assert_006(state, present=False)
        assert_007_absent(state)
        assert_008(state, present=False)
    elif number == "007":
        assert_006(state, present=True)
        assert_007_absent(state)
        assert_008(state, present=False)
    else:
        # 008 comes last, so everything before it must already be in place.
        assert_006(state, present=True)
        if not state["rate_limit_table"]:
            raise GateError("public.rate_limit_hits is absent; apply 007 before 008.")
        assert_008(state, present=False)
    if state["invalid_indexes"]:
        raise GateError("The public schema contains an invalid, unready, or non-live index.")

    statement = migration_sql(number)
    with connection.cursor() as cursor:
        cursor.execute("set statement_timeout = '120s'")
        cursor.execute("set lock_timeout = '5s'")
        cursor.execute(statement)
    return {"migration": number, "applied": True}


def run_verify(connection: psycopg.Connection[Any], number: str) -> dict[str, Any]:
    with (
        connection.transaction(),
        connection.cursor(row_factory=dict_row) as cursor,
    ):
        cursor.execute("set transaction read only")
        cursor.execute("set local statement_timeout = '10s'")
        cursor.execute("set local lock_timeout = '2s'")
        read_only = fetch_one(cursor, "show transaction_read_only")["transaction_read_only"]
        if read_only != "on":
            raise GateError("Read-only transaction guard did not activate.")
        if number == "006":
            state = collect_state(cursor)
            assert_004_005(state)
            assert_006(state, present=True)
            assert_007_absent(state)
            if state["invalid_indexes"]:
                raise GateError(
                    "The public schema contains an invalid, unready, or non-live index."
                )
            result: dict[str, Any] = {"state": state}
        elif number == "008":
            state = collect_state(cursor)
            assert_004_005(state)
            assert_006(state, present=True)
            assert_008(state, present=True)
            if state["invalid_indexes"]:
                raise GateError(
                    "The public schema contains an invalid, unready, or non-live index."
                )
            result = {"state": state}
        else:
            result = collect_007_verification(cursor)
            assert_004_005(result["state"])
            assert_006(result["state"], present=True)
            if result["state"]["invalid_indexes"]:
                raise GateError(
                    "The public schema contains an invalid, unready, or non-live index."
                )
    result["transaction_read_only"] = read_only
    result["migration"] = number
    result["verified"] = True
    return result


def json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "preflight",
            "apply-006",
            "verify-006",
            "apply-007",
            "verify-007",
            "apply-008",
            "verify-008",
        ),
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument(
        "--confirm-project-ref",
        help="Required for apply actions; must match the ref derived from SUPABASE_URL.",
    )
    args = parser.parse_args()

    try:
        direct_url, project_ref = validated_connection(args.env_file.resolve())
        if args.action.startswith("apply-") and args.confirm_project_ref != project_ref:
            raise GateError("Apply requires an exact --confirm-project-ref match.")

        with psycopg.connect(
            direct_url,
            autocommit=True,
            connect_timeout=10,
            application_name="cretona_live_migration_gate",
        ) as connection:
            if args.action == "preflight":
                result = run_preflight(connection)
            elif args.action.startswith("apply-"):
                result = run_apply(connection, args.action.removeprefix("apply-"))
            else:
                result = run_verify(connection, args.action.removeprefix("verify-"))
        print(json.dumps(result, indent=2, default=json_default))
        return 0
    except GateError as exc:
        print(f"GATE FAILED: {exc}", file=sys.stderr)
        return 2
    except psycopg.Error as exc:
        sqlstate = exc.sqlstate or "unknown"
        print(f"DATABASE ERROR: {type(exc).__name__} (SQLSTATE {sqlstate})", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
