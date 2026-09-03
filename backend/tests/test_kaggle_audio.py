"""Audio is opt-in and never allowed to cost a finished video.

Migration 015 made completion fail closed on a missing thumbnail because a
gallery card without a preview is a defect. Audio is the opposite case: it sits
on top of the one thing this project is graded on, and
`PROJECT-PROPOSAL.md` still lists audio mixing under explicit non-scope. So the
failure mode is a silent clip that uploads and completes normally.
"""

from __future__ import annotations

import time
from pathlib import Path
from uuid import UUID

import kaggle_worker
from kaggle_worker import AuthSession, Job, WorkerConfig, run_once

WORKER = UUID("30000000-0000-4000-8000-000000000003")
USER = UUID("10000000-0000-4000-8000-000000000001")
PROJECT = UUID("40000000-0000-4000-8000-000000000004")


def _config(tmp_path: Path) -> WorkerConfig:
    return WorkerConfig(
        database_url="postgresql://worker:secret@localhost/cretona",
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-test-key",
        worker_email="worker@example.com",
        worker_password="secret",
        output_dir=tmp_path,
    )


def _drive(tmp_path: Path, audio_generator) -> list[str]:
    """Run one job to completion and report the ordered side effects."""
    job = Job(PROJECT, USER, "a paper dragon", 5, "16:9")
    events: list[str] = []

    class Database:
        def claim(self, owner: UUID):
            return job

        def heartbeat(self, owner: UUID, claimed: Job, progress: int, message: str):
            return True

        def complete(self, owner: UUID, claimed: Job, sha256: str):
            events.append("complete")
            return True

        def fail(self, *_args):  # pragma: no cover - a silent clip is not a failure
            raise AssertionError("a missing soundtrack must not fail the job")

    class Supabase:
        def session(self):
            return AuthSession("test-token", WORKER, time.monotonic() + 3600)

        def upload_video(self, session: AuthSession, path: str, source: Path):
            events.append("upload-video")

        def upload_thumbnail(self, session: AuthSession, path: str, source: Path):
            events.append("upload-thumbnail")

    def generate(_job: Job, output: Path, _progress, assert_owned):
        assert_owned()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"video" * 300)

    def thumbnail(_video: Path, output: Path):
        output.write_bytes(b"jpeg" * 200)

    assert run_once(_config(tmp_path), Database(), Supabase(), generate, thumbnail, audio_generator)
    return events


def test_audio_is_off_unless_the_flag_is_set(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(kaggle_worker.AUDIO_ENV_VAR, raising=False)
    calls: list[str] = []

    def audio(video: Path, prompt: str, duration: int) -> bool:
        calls.append("audio")
        return True

    events = _drive(tmp_path, audio)

    # An older bundle, or a notebook that never sets the flag, behaves exactly
    # as it does today.
    assert calls == []
    assert events == ["upload-video", "upload-thumbnail", "complete"]


def test_the_flag_turns_audio_on(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(kaggle_worker.AUDIO_ENV_VAR, "1")
    calls: list[tuple[str, int]] = []

    def audio(video: Path, prompt: str, duration: int) -> bool:
        calls.append((prompt, duration))
        return True

    events = _drive(tmp_path, audio)

    # The prompt and duration come from the job, so the soundtrack is about the
    # clip rather than a generic bed.
    assert calls == [("a paper dragon", 5)]
    assert events == ["upload-video", "upload-thumbnail", "complete"]


def test_a_failed_soundtrack_still_ships_the_video(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(kaggle_worker.AUDIO_ENV_VAR, "1")

    def audio(video: Path, prompt: str, duration: int) -> bool:
        return False

    assert _drive(tmp_path, audio) == ["upload-video", "upload-thumbnail", "complete"]


def test_a_raising_soundtrack_is_not_allowed_to_lose_the_video(tmp_path: Path, monkeypatch) -> None:
    """`add_audio` swallows its own errors, but a bug there must not be fatal.

    The job is worth roughly twenty minutes of GPU time by the time audio runs;
    an exception escaping this step would throw that away and refund the user
    for a video that generated correctly.
    """
    monkeypatch.setenv(kaggle_worker.AUDIO_ENV_VAR, "1")

    def audio(video: Path, prompt: str, duration: int) -> bool:
        raise RuntimeError("MMAudio blew up")

    assert _drive(tmp_path, audio) == ["upload-video", "upload-thumbnail", "complete"]


def test_the_audio_prompt_drops_instructions_about_pictures() -> None:
    """Style and camera clauses steer a picture; a soundtrack cannot act on them."""
    composed = (
        "A red paper boat on a calm lake at sunrise, in 8k hyperrealistic "
        "cinematic look, ultra detailed textures, IMAX camera quality, "
        "natural depth of field"
    )

    assert kaggle_worker.audio_prompt(composed) == "A red paper boat on a calm lake at sunrise"


def test_the_audio_prompt_keeps_setting_words_from_a_style_directive() -> None:
    """A cyberpunk street still sounds like rain and a city; that is worth keeping."""
    composed = (
        "a street at night, in cyberpunk 2077 aesthetic, glowing neon lights, "
        "futuristic cityscape, rainy volumetric reflections, dark atmosphere"
    )

    result = kaggle_worker.audio_prompt(composed)

    assert "a street at night" in result
    assert "futuristic cityscape" in result
    assert "rainy volumetric reflections" in result
    assert "aesthetic" not in result


def test_a_prompt_made_only_of_camera_moves_survives_intact() -> None:
    """Filtering to nothing would hand MMAudio an empty string.

    A prompt aimed entirely at the camera is a poor audio prompt, but it still
    beats no prompt at all, so the filter yields rather than empties.
    """
    composed = "camera smoothly orbiting around the subject 360 degrees"

    assert kaggle_worker.audio_prompt(composed) == composed


def test_audio_enabled_reads_the_flag(monkeypatch) -> None:
    for value, expected in (
        ("1", True),
        ("true", True),
        ("YES", True),
        ("0", False),
        ("", False),
        ("off", False),
    ):
        monkeypatch.setenv(kaggle_worker.AUDIO_ENV_VAR, value)
        assert kaggle_worker.audio_enabled() is expected, value

    monkeypatch.delenv(kaggle_worker.AUDIO_ENV_VAR, raising=False)
    assert kaggle_worker.audio_enabled() is False


def test_add_audio_reports_false_when_mmaudio_is_absent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRETONA_MMAUDIO_DIR", str(tmp_path / "nowhere"))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"video" * 300)

    # Returns rather than raises, and leaves the clip untouched.
    assert kaggle_worker.add_audio(clip, "a paper dragon", 4) is False
    assert clip.read_bytes() == b"video" * 300
