from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

import psycopg
import pytest
from psycopg.rows import dict_row

from tests.db_safety import assert_disposable_database

ROOT = Path(__file__).resolve().parents[2]


def load_gate() -> ModuleType:
    path = ROOT / "scripts" / "live-supabase-migration-gate.py"
    spec = importlib.util.spec_from_file_location("live_supabase_migration_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def index(name: str, definition: str) -> dict[str, object]:
    return {
        "indexname": name,
        "indexdef": definition,
        "indisvalid": True,
        "indisready": True,
        "indislive": True,
    }


def migration_state() -> dict[str, object]:
    gate = load_gate()
    indexes = [
        index(
            "idx_admin_audit_logs_action_created",
            "CREATE INDEX ON public.admin_audit_logs (action, created_at DESC, id DESC)",
        ),
        index(
            "idx_admin_audit_logs_actor_created",
            "CREATE INDEX ON public.admin_audit_logs (actor_id, created_at DESC, id DESC)",
        ),
        index(
            "idx_video_projects_provider_job",
            "CREATE INDEX ON public.video_projects (provider, provider_job_id) "
            "WHERE provider_job_id IS NOT NULL",
        ),
        index(
            "idx_video_projects_deleted_user",
            "CREATE INDEX ON public.video_projects (deleted_at, user_id)",
        ),
    ]
    assert set(gate.MIG_011_INDEXES) == {item["indexname"] for item in indexes}
    return {
        "indexes": indexes,
        "profile_columns": {"avatar_path": "text", "gender": "text", "birthday": "text"},
        "profile_constraints": {
            "users_gender_allowed": (
                "CHECK (gender IS NULL OR gender = ANY (ARRAY['male', 'female', 'other']))"
            ),
            "users_birthday_iso_date": "CHECK (birthday IS NULL OR birthday ~ '^date$')",
        },
    }


def test_gate_pins_and_accepts_migrations_011_012_and_014() -> None:
    gate = load_gate()
    state = migration_state()

    assert gate.migration_sql("011")
    assert gate.migration_sql("012")
    assert gate.migration_sql("014")
    gate.assert_011(state, present=True)
    gate.assert_012(state, present=True)


def test_gate_hash_is_stable_across_git_line_endings(tmp_path: Path) -> None:
    gate = load_gate()
    migration = tmp_path / "migration.sql"
    reviewed_lf = b"select 1;\nselect 2;\n"
    migration.write_bytes(reviewed_lf.replace(b"\n", b"\r\n"))
    gate.MIGRATIONS["test-eol"] = (migration, hashlib.sha256(reviewed_lf).hexdigest())

    assert gate.migration_sql("test-eol") == "select 1;\r\nselect 2;\r\n"


def test_gate_detects_missing_profile_column() -> None:
    gate = load_gate()
    state = migration_state()
    state["profile_columns"] = {"avatar_path": "text", "gender": "text"}

    with pytest.raises(gate.GateError, match="MIG-012 is incomplete"):
        gate.assert_012(state, present=True)


def test_gate_allows_valid_partial_index_migration_to_resume() -> None:
    gate = load_gate()
    state = migration_state()
    state["indexes"] = state["indexes"][:1]

    gate.assert_011(state, present=False)
    with pytest.raises(gate.GateError, match="missing indexes"):
        gate.assert_011(state, present=True)


def test_latest_gate_contract_matches_disposable_postgres(postgres_url: str) -> None:
    assert_disposable_database(postgres_url)
    schema_sql = (ROOT / "backend" / "tests" / "postgres_schema.sql").read_text(encoding="utf-8")
    gate = load_gate()
    with psycopg.connect(postgres_url, autocommit=True) as connection:
        connection.execute(schema_sql)
        connection.execute(gate.migration_sql("014"))

    with (
        psycopg.connect(postgres_url, row_factory=dict_row) as connection,
        connection.transaction(),
    ):
        connection.execute("set transaction read only")
        with connection.cursor(row_factory=dict_row) as cursor:
            state = gate.collect_state(cursor)

    assert state["invalid_indexes"] == []
    gate.assert_004_005(state)
    gate.assert_006(state, present=True)
    gate.assert_008(state, present=True)
    gate.assert_009(state, present=True)
    gate.assert_010(state, present=True)
    gate.assert_011(state, present=True)
    gate.assert_012(state, present=True)
    gate.assert_014(state, present=True)

    worker_insert = next(
        policy
        for policy in state["worker_policies"]
        if policy["policyname"] == "videos_worker_insert_leased"
    )
    worker_insert["roles"] = ["authenticated", "anon"]
    with pytest.raises(gate.GateError, match="worker privileges are unsafe"):
        gate.assert_014(state, present=True)
