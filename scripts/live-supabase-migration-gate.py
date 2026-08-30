"""Guarded preflight, apply, and verification for Cretona migrations 006-014.

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
DEFAULT_ENV_FILE = ROOT / ".env" if (ROOT / ".env").exists() else ROOT / "env"
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
    "009": (
        ROOT / "supabase" / "009_add_progress_tracking.sql",
        "dc423f5a00fc5887df61ae1200c52d2228b942d680329b55bdecd7529bcb7e11",
    ),
    "010": (
        ROOT / "supabase" / "010_add_user_avatar.sql",
        "6cfdbcac48db577f4646862b5bd121354118ff72813b5d20021dbc211c32d198",
    ),
    "011": (
        ROOT / "supabase" / "011_add_composite_query_indexes.sql",
        "276b2f5044a205a6e180eebebdd4c0448aba3196b20278e231afe5eace2f959b",
    ),
    "012": (
        ROOT / "supabase" / "012_add_user_profile_fields.sql",
        "00b138555e4f59f0f9910a1285a8ac2c88f3f17a3e8e13d51c083e61c5d012e7",
    ),
    "014": (
        ROOT / "supabase" / "014_add_kaggle_worker.sql",
        "8e91ea80e4765821058c802637f149c78d2c79cc3665f589343f2c26cebb6bc3",
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
    # Git may materialize the same reviewed text as LF or CRLF depending on
    # checkout policy. Pin semantic file content, not the host's newline bytes;
    # otherwise a gate proven on Windows can reject the identical Git blob in CI.
    canonical_payload = payload.replace(b"\r\n", b"\n")
    observed_hash = hashlib.sha256(canonical_payload).hexdigest()
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
              ('started_at', 'lease_owner', 'lease_expires_at',
               'progress_percent', 'step_message'))
            or (table_name = 'users' and column_name in
              ('avatar_path', 'gender', 'birthday'))
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
            'idx_rate_limit_caller_window', 'idx_rate_limit_cleanup',
            'idx_admin_audit_logs_action_created',
            'idx_admin_audit_logs_actor_created',
            'idx_video_projects_provider_job',
            'idx_video_projects_deleted_user'
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
          to_regclass('public.credit_transactions') is not null as credit_transactions_table,
          to_regclass('supabase_migrations.schema_migrations') is not null as cli_history
        """,
    )
    # MIG-009 changes a constraint as well as adding columns, and the enum
    # branch only fires where project_status is an enum type. Read all three so
    # a half-applied 009 is visible rather than inferred from the columns.
    error_code_constraint = cursor.execute(
        """
        select pg_get_constraintdef(oid) as definition
        from pg_constraint
        where conrelid = 'public.video_projects'::regclass
          and conname = 'chk_error_code'
        """
    ).fetchone()
    profile_constraints = cursor.execute(
        """
        select conname, pg_get_constraintdef(oid) as definition
        from pg_constraint
        where conrelid = 'public.users'::regclass
          and conname in ('users_gender_allowed', 'users_birthday_iso_date')
        order by conname
        """
    ).fetchall()
    status_enum_labels = [
        row["label"]
        for row in cursor.execute(
            """
            select e.enumlabel as label
            from pg_type t
            join pg_enum e on e.enumtypid = t.oid
            where t.typname = 'project_status'
            order by e.enumsortorder
            """
        ).fetchall()
    ]
    worker_role = fetch_one(
        cursor,
        """
        select r.oid is not null as present,
               coalesce(r.rolcanlogin, false) as can_login,
               coalesce(r.rolinherit, true) as inherits,
               coalesce(r.rolsuper, false) as superuser,
               coalesce(r.rolcreaterole, false) as create_role,
               coalesce(r.rolcreatedb, false) as create_db,
               coalesce(r.rolbypassrls, false) as bypass_rls,
               coalesce(r.rolreplication, false) as replication,
               coalesce(
                 exists(select 1 from pg_auth_members m where m.member = r.oid), false
               ) as role_membership,
               coalesce(
                 has_table_privilege(
                   r.oid, 'public.video_projects', 'SELECT,INSERT,UPDATE,DELETE'
                 )
                 or has_table_privilege(
                   r.oid, 'public.users', 'SELECT,INSERT,UPDATE,DELETE'
                 )
                 or has_table_privilege(
                   r.oid, 'public.credit_transactions', 'SELECT,INSERT,UPDATE,DELETE'
                 )
                 or has_table_privilege(
                   r.oid, 'public.generation_logs', 'SELECT,INSERT,UPDATE,DELETE'
                 )
                 or has_table_privilege(
                   r.oid, 'storage.objects', 'SELECT,INSERT,UPDATE,DELETE'
                 ), false
               ) as table_access
        from (select 1) sentinel
        left join pg_roles r on r.rolname = 'cretona_kaggle_worker'
        """,
    )
    worker_functions = cursor.execute(
        """
        select p.proname, p.prosecdef,
               coalesce(has_function_privilege(worker.oid, p.oid, 'EXECUTE'), false)
                 as worker_execute,
               coalesce(has_function_privilege(anon_role.oid, p.oid, 'EXECUTE'), false)
                 as anon_execute,
               coalesce(has_function_privilege(auth_role.oid, p.oid, 'EXECUTE'), false)
                 as authenticated_execute
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        left join pg_roles worker on worker.rolname = 'cretona_kaggle_worker'
        left join pg_roles anon_role on anon_role.rolname = 'anon'
        left join pg_roles auth_role on auth_role.rolname = 'authenticated'
        where n.nspname = 'private'
          and p.proname in (
            'cretona_kaggle_claim_job', 'cretona_kaggle_heartbeat',
            'cretona_kaggle_complete', 'cretona_kaggle_fail',
            'cretona_kaggle_can_write_object'
          )
        order by p.proname
        """
    ).fetchall()
    worker_policies = cursor.execute(
        """
        select policyname, cmd, roles, qual, with_check
        from pg_policies
        where schemaname = 'storage' and tablename = 'objects'
          and policyname in (
            'videos_worker_insert_leased', 'videos_worker_select_leased',
            'videos_worker_update_leased'
          )
        order by policyname
        """
    ).fetchall()
    return {
        "server": server,
        "columns": columns,
        "indexes": indexes,
        "invalid_indexes": invalid_indexes,
        "rate_limit_table": table_state["rate_limit_table"],
        "audit_table": table_state["audit_table"],
        "credit_transactions_table": table_state["credit_transactions_table"],
        "cli_history": table_state["cli_history"],
        "error_code_constraint": (
            error_code_constraint["definition"] if error_code_constraint else None
        ),
        "status_enum_labels": status_enum_labels,
        "profile_columns": {
            row["column_name"]: row["udt_name"] for row in columns if row["table_name"] == "users"
        },
        "profile_constraints": {row["conname"]: row["definition"] for row in profile_constraints},
        "worker_role": worker_role,
        "worker_functions": worker_functions,
        "worker_policies": worker_policies,
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


# progress_percent holds 0-100. The migration declares smallint, but any wider
# integer stores those values exactly, so demanding int2 would fail a database
# that is functionally correct. Live is int4 — the column pre-dated 009 there,
# so `add column if not exists` left the existing width alone.
PROGRESS_INT_TYPES = ("int2", "int4", "int8")


def state_009(state: dict[str, Any]) -> dict[str, Any]:
    """What 009 changed, read back in the three places it changed them."""
    observed = {
        (row["table_name"], row["column_name"]): row["udt_name"] for row in state["columns"]
    }
    progress = observed.get(("video_projects", "progress_percent"))
    step_message = observed.get(("video_projects", "step_message"))
    definition = state["error_code_constraint"]
    labels = state["status_enum_labels"]
    return {
        "columns_present": progress in PROGRESS_INT_TYPES and step_message == "text",
        # Reported rather than asserted, so a genuine type surprise is still
        # visible instead of being hidden by the tolerance above.
        "progress_percent_type": progress,
        "step_message_type": step_message,
        "progress_percent_matches_migration": progress == "int2",
        "constraint_present": definition is not None,
        "constraint_allows_cancelled": bool(definition) and "cancelled" in definition,
        "constraint_definition": definition,
        # No enum means the column is text and the branch was a no-op, which is
        # a pass rather than a gap.
        "status_enum_present": bool(labels),
        "status_enum_allows_cancelled": (not labels) or ("cancelled" in labels),
        "status_enum_labels": labels,
    }


def assert_009(state: dict[str, Any], *, present: bool) -> None:
    """009 is applied only when every half of it is.

    A database can hold the columns and still reject a cancellation: the
    `add column if not exists` half succeeds independently of the constraint
    swap. Treating "columns exist" as "009 applied" is how a cancel path passes
    a schema check and then fails on the first real user.
    """
    facts = state_009(state)
    applied = (
        facts["columns_present"]
        and facts["constraint_allows_cancelled"]
        and facts["status_enum_allows_cancelled"]
    )
    if present and not applied:
        missing = []
        if not facts["columns_present"]:
            missing.append(
                "progress_percent/step_message "
                f"(observed {facts['progress_percent_type']}/{facts['step_message_type']})"
            )
        if not facts["constraint_allows_cancelled"]:
            missing.append("chk_error_code allowing 'cancelled'")
        if not facts["status_enum_allows_cancelled"]:
            missing.append("project_status enum value 'cancelled'")
        raise GateError(f"MIG-009 is incomplete; missing: {', '.join(missing)}.")
    if not present and applied:
        raise GateError("MIG-009 is already fully applied; refusing an unplanned re-apply.")


def assert_010(state: dict[str, Any], *, present: bool) -> None:
    """public.users.avatar_path, added by MIG-010."""
    observed = state["profile_columns"].get("avatar_path")
    if present and observed != "text":
        raise GateError(
            "public.users.avatar_path is "
            f"{'missing' if observed is None else f'the wrong type ({observed})'}."
        )
    if not present and observed is not None:
        raise GateError("MIG-010 is already applied; refusing an unplanned re-apply.")


MIG_011_INDEXES = {
    "idx_admin_audit_logs_action_created": (
        "admin_audit_logs",
        "action",
        "created_at",
        "id",
    ),
    "idx_admin_audit_logs_actor_created": (
        "admin_audit_logs",
        "actor_id",
        "created_at",
        "id",
    ),
    "idx_video_projects_provider_job": (
        "video_projects",
        "provider",
        "provider_job_id",
        "provider_job_id is not null",
    ),
    "idx_video_projects_deleted_user": (
        "video_projects",
        "deleted_at",
        "user_id",
    ),
}


def assert_011(state: dict[str, Any], *, present: bool) -> None:
    """Composite query indexes added by MIG-011."""
    indexes = index_by_name(state)
    existing = MIG_011_INDEXES.keys() & indexes.keys()
    for name in existing:
        assert_index(indexes, name, MIG_011_INDEXES[name])

    fully_applied = len(existing) == len(MIG_011_INDEXES)
    if present and not fully_applied:
        missing = sorted(MIG_011_INDEXES.keys() - existing)
        raise GateError(f"MIG-011 is incomplete; missing indexes: {', '.join(missing)}.")
    if not present and fully_applied:
        raise GateError("MIG-011 is already fully applied; refusing an unplanned re-apply.")


def state_012(state: dict[str, Any]) -> dict[str, Any]:
    columns = state["profile_columns"]
    constraints = state["profile_constraints"]
    gender_definition = constraints.get("users_gender_allowed", "").casefold()
    birthday_definition = constraints.get("users_birthday_iso_date", "").casefold()
    return {
        "gender_type": columns.get("gender"),
        "birthday_type": columns.get("birthday"),
        "gender_constraint_valid": all(
            fragment in gender_definition for fragment in ("gender", "male", "female", "other")
        ),
        "birthday_constraint_valid": "birthday" in birthday_definition
        and "~" in birthday_definition,
    }


def assert_012(state: dict[str, Any], *, present: bool) -> None:
    """Optional user profile fields and checks added by MIG-012."""
    facts = state_012(state)
    fully_applied = (
        facts["gender_type"] == "text"
        and facts["birthday_type"] == "text"
        and facts["gender_constraint_valid"]
        and facts["birthday_constraint_valid"]
    )
    if present and not fully_applied:
        raise GateError("MIG-012 is incomplete or has an unexpected column/constraint contract.")
    if not present and fully_applied:
        raise GateError("MIG-012 is already fully applied; refusing an unplanned re-apply.")

    # The migration is idempotent, so a valid partial application may resume.
    # Wrong existing objects would survive IF NOT EXISTS and must stop first.
    for name in ("gender_type", "birthday_type"):
        if facts[name] not in (None, "text"):
            raise GateError(f"MIG-012 cannot repair unexpected {name}={facts[name]!r}.")
    constraints = state["profile_constraints"]
    if "users_gender_allowed" in constraints and not facts["gender_constraint_valid"]:
        raise GateError("MIG-012 cannot repair the existing users_gender_allowed constraint.")
    if "users_birthday_iso_date" in constraints and not facts["birthday_constraint_valid"]:
        raise GateError("MIG-012 cannot repair the existing users_birthday_iso_date constraint.")


WORKER_FUNCTIONS = {
    "cretona_kaggle_claim_job",
    "cretona_kaggle_heartbeat",
    "cretona_kaggle_complete",
    "cretona_kaggle_fail",
}
WORKER_POLICIES = {
    "videos_worker_insert_leased": "INSERT",
    "videos_worker_select_leased": "SELECT",
    "videos_worker_update_leased": "UPDATE",
}


def state_014(state: dict[str, Any]) -> dict[str, Any]:
    def leased_video_scope(expression: Any) -> bool:
        text = str(expression or "")
        return (
            "bucket_id" in text and "'videos'" in text and "cretona_kaggle_can_write_object" in text
        )

    functions = {row["proname"]: row for row in state["worker_functions"]}
    policies = {row["policyname"]: row for row in state["worker_policies"]}
    role = state["worker_role"]
    work_functions_secure = all(
        name in functions
        and functions[name]["prosecdef"]
        and functions[name]["worker_execute"]
        and not functions[name]["anon_execute"]
        and not functions[name]["authenticated_execute"]
        for name in WORKER_FUNCTIONS
    )
    helper = functions.get("cretona_kaggle_can_write_object")
    helper_secure = bool(
        helper
        and helper["prosecdef"]
        and not helper["anon_execute"]
        and helper["authenticated_execute"]
    )
    policies_secure = all(
        name in policies
        and policies[name]["cmd"] == command
        and set(policies[name]["roles"]) == {"authenticated"}
        and (
            (command == "INSERT" and leased_video_scope(policies[name]["with_check"]))
            or (command == "SELECT" and leased_video_scope(policies[name]["qual"]))
            or (
                command == "UPDATE"
                and leased_video_scope(policies[name]["qual"])
                and leased_video_scope(policies[name]["with_check"])
            )
        )
        for name, command in WORKER_POLICIES.items()
    )
    role_secure = bool(role["present"] and role["can_login"] and not role["inherits"]) and not any(
        role[name]
        for name in (
            "superuser",
            "create_role",
            "create_db",
            "bypass_rls",
            "replication",
            "role_membership",
            "table_access",
        )
    )
    return {
        "role_secure": role_secure,
        "work_functions_secure": work_functions_secure,
        "storage_helper_secure": helper_secure,
        "storage_policies_secure": policies_secure,
    }


def assert_014(state: dict[str, Any], *, present: bool) -> None:
    facts = state_014(state)
    fully_applied = all(facts.values())
    any_present = bool(
        state["worker_role"]["present"] or state["worker_functions"] or state["worker_policies"]
    )
    if present and not fully_applied:
        raise GateError("MIG-014 is incomplete or its worker privileges are unsafe.")
    if not present and any_present:
        raise GateError("MIG-014 is already present or partially applied; refusing re-apply.")


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


def run_status(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    """Report what is applied without asserting anything.

    `preflight` and `verify-*` answer "is this the state I expected"; they exit
    non-zero when it is not, which is the wrong shape for the question "is 009
    applied at all". This answers that one.
    """
    state = read_only_state(connection)
    indexes = index_by_name(state)
    facts = state_009(state)
    profile_facts = state_012(state)
    worker_facts = state_014(state)
    return {
        "transaction_read_only": state["transaction_read_only"],
        "server_version": state["server"]["version"],
        "migrations": {
            "006": "idx_logs_retention" in indexes,
            "007": bool(state["rate_limit_table"]),
            "008": bool(state["audit_table"]),
            "009": (
                facts["columns_present"]
                and facts["constraint_allows_cancelled"]
                and facts["status_enum_allows_cancelled"]
            ),
            "010": state["profile_columns"].get("avatar_path") == "text",
            "011": all(name in indexes for name in MIG_011_INDEXES),
            "012": (
                profile_facts["gender_type"] == "text"
                and profile_facts["birthday_type"] == "text"
                and profile_facts["gender_constraint_valid"]
                and profile_facts["birthday_constraint_valid"]
            ),
            "013": bool(state["credit_transactions_table"]),
            "014": all(worker_facts.values()),
        },
        "migration_009": facts,
        "migration_012": profile_facts,
        "migration_014": worker_facts,
        "invalid_indexes": state["invalid_indexes"],
    }


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
    elif number == "008":
        assert_006(state, present=True)
        if not state["rate_limit_table"]:
            raise GateError("public.rate_limit_hits is absent; apply 007 before 008.")
        assert_008(state, present=False)
    elif number == "009":
        assert_006(state, present=True)
        if not state["rate_limit_table"]:
            raise GateError("public.rate_limit_hits is absent; apply 007 before 009.")
        assert_008(state, present=True)
        assert_009(state, present=False)
    elif number == "010":
        assert_006(state, present=True)
        assert_008(state, present=True)
        assert_009(state, present=True)
        assert_010(state, present=False)
    elif number == "011":
        assert_006(state, present=True)
        assert_008(state, present=True)
        assert_009(state, present=True)
        assert_010(state, present=True)
        assert_011(state, present=False)
    elif number == "012":
        assert_006(state, present=True)
        assert_008(state, present=True)
        assert_009(state, present=True)
        assert_010(state, present=True)
        assert_011(state, present=True)
        assert_012(state, present=False)
    else:
        assert_006(state, present=True)
        assert_008(state, present=True)
        assert_009(state, present=True)
        assert_010(state, present=True)
        assert_011(state, present=True)
        assert_012(state, present=True)
        if not state["credit_transactions_table"]:
            raise GateError("public.credit_transactions is absent; apply 013 before 014.")
        assert_014(state, present=False)
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
        elif number == "009":
            state = collect_state(cursor)
            assert_004_005(state)
            assert_006(state, present=True)
            assert_008(state, present=True)
            assert_009(state, present=True)
            if state["invalid_indexes"]:
                raise GateError(
                    "The public schema contains an invalid, unready, or non-live index."
                )
            result = {"state": state, "migration_009": state_009(state)}
        elif number == "010":
            state = collect_state(cursor)
            assert_004_005(state)
            assert_009(state, present=True)
            assert_010(state, present=True)
            if state["invalid_indexes"]:
                raise GateError(
                    "The public schema contains an invalid, unready, or non-live index."
                )
            result = {
                "state": state,
                "avatar_column": state["profile_columns"].get("avatar_path"),
            }
        elif number == "011":
            state = collect_state(cursor)
            assert_004_005(state)
            assert_009(state, present=True)
            assert_010(state, present=True)
            assert_011(state, present=True)
            if state["invalid_indexes"]:
                raise GateError(
                    "The public schema contains an invalid, unready, or non-live index."
                )
            result = {"state": state}
        elif number == "012":
            state = collect_state(cursor)
            assert_004_005(state)
            assert_009(state, present=True)
            assert_010(state, present=True)
            assert_011(state, present=True)
            assert_012(state, present=True)
            if state["invalid_indexes"]:
                raise GateError(
                    "The public schema contains an invalid, unready, or non-live index."
                )
            result = {"state": state, "migration_012": state_012(state)}
        elif number == "014":
            state = collect_state(cursor)
            assert_004_005(state)
            assert_012(state, present=True)
            if not state["credit_transactions_table"]:
                raise GateError("public.credit_transactions is absent; migration 013 is required.")
            assert_014(state, present=True)
            if state["invalid_indexes"]:
                raise GateError(
                    "The public schema contains an invalid, unready, or non-live index."
                )
            result = {"state": state, "migration_014": state_014(state)}
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
            "status",
            "apply-006",
            "verify-006",
            "apply-007",
            "verify-007",
            "apply-008",
            "verify-008",
            "apply-009",
            "verify-009",
            "apply-010",
            "verify-010",
            "apply-011",
            "verify-011",
            "apply-012",
            "verify-012",
            "apply-014",
            "verify-014",
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
            elif args.action == "status":
                result = run_status(connection)
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
