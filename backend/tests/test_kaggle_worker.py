from __future__ import annotations

import ast
import inspect
import time
from pathlib import Path
from uuid import UUID

import kaggle_worker
from kaggle_worker import (
    AuthSession,
    Job,
    WorkerConfig,
    WorkerDatabase,
    dimensions,
    frame_count,
    run_once,
    storage_path,
    thumbnail_path,
)

WORKER = UUID("30000000-0000-4000-8000-000000000003")
USER = UUID("10000000-0000-4000-8000-000000000001")
PROJECT = UUID("40000000-0000-4000-8000-000000000004")


def test_model_loaders_use_the_diffusers_precision_keyword() -> None:
    tree = ast.parse(inspect.getsource(kaggle_worker))
    precision_keywords = [
        keyword.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "from_pretrained"
        for keyword in node.keywords
        if keyword.arg in {"dtype", "torch_dtype"}
    ]

    assert precision_keywords.count("torch_dtype") == 3
    assert "dtype" not in precision_keywords


def test_wan_profile_matches_the_proven_contract() -> None:
    job = Job(PROJECT, USER, "a paper dragon", 5, "16:9")

    assert frame_count(5) == 81
    assert dimensions("16:9") == (832, 480)
    assert dimensions("9:16") == (480, 832)
    assert storage_path(job) == f"{USER}/{PROJECT}/video.mp4"
    assert thumbnail_path(job) == f"{USER}/{PROJECT}/thumbnail.jpg"


def test_one_job_uploads_before_it_is_completed(tmp_path: Path) -> None:
    job = Job(PROJECT, USER, "a paper dragon", 5, "16:9")
    events: list[str] = []

    class Database:
        def claim(self, owner: UUID):
            assert owner == WORKER
            return job

        def heartbeat(self, owner: UUID, claimed: Job, progress: int, message: str):
            assert owner == WORKER and claimed == job and progress >= 1 and message
            return True

        def complete(self, owner: UUID, claimed: Job, sha256: str):
            assert owner == WORKER and claimed == job and len(sha256) == 64
            events.append("complete")
            return True

        def fail(self, *_args):  # pragma: no cover - failure would fail this test
            raise AssertionError("successful job was marked failed")

    class Supabase:
        def session(self):
            return AuthSession("test-token", WORKER, time.monotonic() + 3600)

        def upload_video(self, session: AuthSession, path: str, source: Path):
            assert session.user_id == WORKER
            assert path == f"{USER}/{PROJECT}/video.mp4"
            assert source.stat().st_size > 1024
            events.append("upload-video")

        def upload_thumbnail(self, session: AuthSession, path: str, source: Path):
            assert session.user_id == WORKER
            assert path == f"{USER}/{PROJECT}/thumbnail.jpg"
            assert source.stat().st_size > 512
            events.append("upload-thumbnail")

    def generate(_job: Job, output: Path, _progress, assert_owned):
        assert_owned()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"video" * 300)

    def thumbnail(_video: Path, output: Path):
        output.write_bytes(b"jpeg" * 200)

    config = WorkerConfig(
        database_url="postgresql://worker:secret@localhost/cretona",
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-test-key",
        worker_email="worker@example.com",
        worker_password="secret",
        output_dir=tmp_path,
    )

    assert run_once(config, Database(), Supabase(), generate, thumbnail) is True
    assert events == ["upload-video", "upload-thumbnail", "complete"]


def test_a_malformed_claim_is_failed_instead_of_crashing_the_worker() -> None:
    class Database(WorkerDatabase):
        def __init__(self) -> None:
            self.calls = 0

        def _fetchone(self, _statement, parameters):
            self.calls += 1
            if self.calls == 1:
                return {
                    "project_id": PROJECT,
                    "user_id": USER,
                    "prompt": "a dragon",
                    "duration_seconds": 10,
                    "aspect_ratio": "16:9",
                }
            assert parameters == (
                WORKER,
                PROJECT,
                "invalid_input",
                "Unsupported Kaggle job options.",
            )
            return {"ok": True}

    database = Database()

    assert database.claim(WORKER) is None
    assert database.calls == 2


def _refusal_case(tmp_path: Path, *, still_owned: bool) -> list[str]:
    """Drive run_once to a refused completion and report what it did about it."""
    job = Job(PROJECT, USER, "a paper dragon", 5, "16:9")
    events: list[str] = []

    class Database:
        def claim(self, owner: UUID):
            return job

        def heartbeat(self, owner: UUID, claimed: Job, progress: int, message: str):
            assert owner == WORKER and claimed == job
            # The lease probe after a refusal reuses this call, so it must stay
            # inside the range migration 014 accepts.
            assert 1 <= progress <= 95 and message
            # Ownership only lapses at the probe. Returning False earlier would
            # stop the job before it ever reached completion and prove nothing.
            return still_owned if "complete-refused" in events else True

        def complete(self, owner: UUID, claimed: Job, sha256: str):
            events.append("complete-refused")
            return False

        def fail(self, owner: UUID, claimed: Job, code: str, message: str):
            assert owner == WORKER and claimed == job and code == "provider_error"
            events.append("fail")
            return True

    class Supabase:
        def session(self):
            return AuthSession("test-token", WORKER, time.monotonic() + 3600)

        def upload_video(self, session: AuthSession, path: str, source: Path):
            pass

        def upload_thumbnail(self, session: AuthSession, path: str, source: Path):
            pass

    def generate(_job: Job, output: Path, _progress, assert_owned):
        assert_owned()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"video" * 300)

    def thumbnail(_video: Path, output: Path):
        output.write_bytes(b"jpeg" * 200)

    config = WorkerConfig(
        database_url="postgresql://worker:secret@localhost/cretona",
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-test-key",
        worker_email="worker@example.com",
        worker_password="secret",
        output_dir=tmp_path,
    )
    assert run_once(config, Database(), Supabase(), generate, thumbnail) is True
    return events


def test_a_refused_completion_refunds_while_the_lease_is_still_held(tmp_path: Path) -> None:
    """A missing object is this worker's failure, so the charge must come back.

    MIG-015 lets completion refuse for a second reason, and reading that as a
    lost lease would leave the user charged for a job nobody finishes.
    """
    assert _refusal_case(tmp_path, still_owned=True) == ["complete-refused", "fail"]


def test_a_refused_completion_leaves_a_lost_lease_to_its_new_owner(tmp_path: Path) -> None:
    """The original meaning still holds: another worker owns the outcome."""
    assert _refusal_case(tmp_path, still_owned=False) == ["complete-refused"]
