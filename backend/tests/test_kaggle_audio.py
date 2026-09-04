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


# --- muxing instead of accepting MMAudio's re-encode -------------------------
#
# MMAudio composites by re-encoding the picture. Measured on two real worker
# jobs (docs/evidence/EXP006_FIRST_AUDIO_JOBS_2026-09-03.md), a 405,459 B clip
# came back at 2.9-5.1 MB while the soundtrack itself was about 64 KB. The
# worker therefore keeps MMAudio's audio and Wan2.1's original picture.

SILENT_CLIP = b"wan21-picture" * 200
MMAUDIO_CLIP = b"mmaudio-reencoded-picture-and-sound" * 400
MUXED_CLIP = b"original-picture-plus-sound" * 100


def _mmaudio_repo(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "MMAudio"
    repo.mkdir()
    (repo / "demo.py").write_text("# stand-in for MMAudio\n", encoding="utf-8")
    monkeypatch.setenv("CRETONA_MMAUDIO_DIR", str(repo))
    monkeypatch.setattr(kaggle_worker, "_ffmpeg_executable", lambda: "ffmpeg")
    return repo


def _stub_subprocess(monkeypatch, repo: Path, *, mux_succeeds: bool) -> list[list[str]]:
    """Answer for both subprocess calls and record the argv of each."""
    seen: list[list[str]] = []

    class Completed:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode
            self.stdout = ""
            self.stderr = "" if returncode == 0 else "stream mapping failed"

    def fake_run(args, **_kwargs):
        argv = [str(a) for a in args]
        seen.append(argv)
        if any(a.endswith("demo.py") for a in argv):
            produced = repo / "output" / "clip.mp4"
            produced.parent.mkdir(parents=True, exist_ok=True)
            produced.write_bytes(MMAUDIO_CLIP)
            return Completed(0)
        if not mux_succeeds:
            return Completed(1)
        Path(argv[-1]).write_bytes(MUXED_CLIP)
        return Completed(0)

    monkeypatch.setattr("subprocess.run", fake_run)
    return seen


def test_the_soundtrack_is_muxed_onto_the_original_picture(tmp_path: Path, monkeypatch) -> None:
    repo = _mmaudio_repo(tmp_path, monkeypatch)
    _stub_subprocess(monkeypatch, repo, mux_succeeds=True)
    clip = tmp_path / "video.mp4"
    clip.write_bytes(SILENT_CLIP)

    assert kaggle_worker.add_audio(clip, "a paper dragon", 4) is True

    # The clip that ships is the mux, not the file MMAudio re-encoded.
    assert clip.read_bytes() == MUXED_CLIP
    assert not (repo / "output" / "clip.mp4").exists()
    assert not (tmp_path / "video.mp4.mux.mp4").exists()


def test_the_mux_copies_both_streams_rather_than_re_encoding(tmp_path: Path, monkeypatch) -> None:
    """This is the whole point of the step, so it is asserted rather than assumed.

    Re-encoding here would spend seven times the bitrate to preserve the
    artefacts of the first encode. `-c:v copy` is what keeps the picture
    identical to what Wan2.1 wrote, and `-c:a copy` avoids a second lossy pass
    over sound that is already AAC.
    """
    repo = _mmaudio_repo(tmp_path, monkeypatch)
    calls = _stub_subprocess(monkeypatch, repo, mux_succeeds=True)
    clip = tmp_path / "video.mp4"
    clip.write_bytes(SILENT_CLIP)

    kaggle_worker.add_audio(clip, "a paper dragon", 4)

    ffmpeg = next(argv for argv in calls if argv[0] == "ffmpeg")
    assert "-c:v" in ffmpeg and ffmpeg[ffmpeg.index("-c:v") + 1] == "copy"
    assert "-c:a" in ffmpeg and ffmpeg[ffmpeg.index("-c:a") + 1] == "copy"
    # Picture from the untouched original, sound from MMAudio's composite.
    assert ffmpeg[ffmpeg.index("-map") + 1] == "0:v:0"
    assert ffmpeg[ffmpeg.index("-map", ffmpeg.index("-map") + 1) + 1] == "1:a:0"
    # The index belongs at the front for progressive playback over a tunnel.
    assert ffmpeg[ffmpeg.index("-movflags") + 1] == "+faststart"
    # `-shortest` looks harmless next to two streams of near-equal length and
    # is not: MMAudio returns 4.040 s of sound for a 4.0625 s clip, and asking
    # ffmpeg to reconcile that cost four frames of picture -- 65 became 61 on
    # a real worker clip. The video is what the project is graded on.
    assert "-shortest" not in ffmpeg


def test_a_failed_mux_keeps_the_soundtrack_rather_than_the_original(
    tmp_path: Path, monkeypatch
) -> None:
    """Falling back costs file size; falling back to silence would cost the feature.

    By the time the mux runs, the soundtrack has already cost about three
    minutes of GPU time. A bigger clip that plays with sound is worth more than
    a smaller one that plays without it.
    """
    repo = _mmaudio_repo(tmp_path, monkeypatch)
    _stub_subprocess(monkeypatch, repo, mux_succeeds=False)
    clip = tmp_path / "video.mp4"
    clip.write_bytes(SILENT_CLIP)

    assert kaggle_worker.add_audio(clip, "a paper dragon", 4) is True

    assert clip.read_bytes() == MMAUDIO_CLIP
    assert not (tmp_path / "video.mp4.mux.mp4").exists()


def test_the_mux_is_skipped_when_no_ffmpeg_exists(tmp_path: Path, monkeypatch) -> None:
    repo = _mmaudio_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(kaggle_worker, "_ffmpeg_executable", lambda: None)
    calls = _stub_subprocess(monkeypatch, repo, mux_succeeds=True)
    clip = tmp_path / "video.mp4"
    clip.write_bytes(SILENT_CLIP)

    assert kaggle_worker.add_audio(clip, "a paper dragon", 4) is True

    # MMAudio ran, ffmpeg never did, and the clip still has sound.
    assert [argv[0] for argv in calls if argv[0] == "ffmpeg"] == []
    assert clip.read_bytes() == MMAUDIO_CLIP


def test_mux_audio_removes_a_partial_file_when_ffmpeg_fails(tmp_path: Path, monkeypatch) -> None:
    """A half-written container must not be mistaken for a finished clip."""
    monkeypatch.setattr(kaggle_worker, "_ffmpeg_executable", lambda: "ffmpeg")
    destination = tmp_path / "out.mp4"

    class Completed:
        returncode = 3
        stdout = ""
        stderr = "Invalid data found when processing input"

    def fake_run(args, **_kwargs):
        Path(str(args[-1])).write_bytes(b"truncated")
        return Completed()

    monkeypatch.setattr("subprocess.run", fake_run)

    assert kaggle_worker.mux_audio(tmp_path / "a.mp4", tmp_path / "b.mp4", destination) is False
    assert not destination.exists()


def test_mux_audio_rejects_an_empty_result(tmp_path: Path, monkeypatch) -> None:
    """ffmpeg can exit 0 having written nothing usable; size is the second check."""
    monkeypatch.setattr(kaggle_worker, "_ffmpeg_executable", lambda: "ffmpeg")
    destination = tmp_path / "out.mp4"

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(args, **_kwargs):
        Path(str(args[-1])).write_bytes(b"tiny")
        return Completed()

    monkeypatch.setattr("subprocess.run", fake_run)

    assert kaggle_worker.mux_audio(tmp_path / "a.mp4", tmp_path / "b.mp4", destination) is False
    assert not destination.exists()
