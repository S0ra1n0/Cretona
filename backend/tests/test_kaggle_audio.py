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


MEASURED_JSON = """[Parsed_loudnorm_0 @ 000]
{
	"input_i" : "-29.44",
	"input_tp" : "-6.72",
	"input_lra" : "4.00",
	"input_thresh" : "-39.50",
	"output_i" : "-16.86",
	"output_tp" : "-1.50",
	"output_lra" : "1.70",
	"output_thresh" : "-26.86",
	"normalization_type" : "dynamic",
	"target_offset" : "0.86"
}"""


def _is_measurement(argv: list[str]) -> bool:
    """The analysis pass writes nothing; the mux writes a file."""
    return "-f" in argv and argv[argv.index("-f") + 1] == "null"


def _stub_subprocess(
    monkeypatch,
    repo: Path,
    *,
    mux_succeeds: bool,
    measurement: str | None = MEASURED_JSON,
) -> list[list[str]]:
    """Answer all three subprocess calls and record the argv of each.

    `measurement=None` stands for an ffmpeg that cannot report loudness, which
    must degrade to an unnormalised mux rather than to silence.
    """
    seen: list[list[str]] = []

    class Completed:
        def __init__(self, returncode: int, stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = ""
            self.stderr = stderr or ("" if returncode == 0 else "stream mapping failed")

    def fake_run(args, **_kwargs):
        argv = [str(a) for a in args]
        seen.append(argv)
        if any(a.endswith("demo.py") for a in argv):
            produced = repo / "output" / "clip.mp4"
            produced.parent.mkdir(parents=True, exist_ok=True)
            produced.write_bytes(MMAUDIO_CLIP)
            return Completed(0)
        if _is_measurement(argv):
            return Completed(0, measurement or "no json here")
        if not mux_succeeds:
            return Completed(1)
        Path(argv[-1]).write_bytes(MUXED_CLIP)
        return Completed(0)

    monkeypatch.setattr("subprocess.run", fake_run)
    return seen


def _mux_call(calls: list[list[str]]) -> list[str]:
    return next(argv for argv in calls if argv[0] == "ffmpeg" and not _is_measurement(argv))


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
    identical to what Wan2.1 wrote. The audio is the deliberate exception: it is
    re-encoded so it can be normalised, because 64 KB of AAC costs nothing next
    to the picture and MMAudio's level is too low to hear on a phone.
    """
    repo = _mmaudio_repo(tmp_path, monkeypatch)
    calls = _stub_subprocess(monkeypatch, repo, mux_succeeds=True)
    clip = tmp_path / "video.mp4"
    clip.write_bytes(SILENT_CLIP)

    kaggle_worker.add_audio(clip, "a paper dragon", 4)

    ffmpeg = _mux_call(calls)
    assert "-c:v" in ffmpeg and ffmpeg[ffmpeg.index("-c:v") + 1] == "copy"
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


# --- the prompt MMAudio actually receives ------------------------------------
#
# The tests above this line were written against the shape EXP-006's notebook
# used -- subject first, style clauses after a comma -- which is not what the
# app produces. `PromptService` emits
#
#     Cinematic <ratio> video of <subject>. Clear subject motion, coherent
#     environment, smooth camera movement, natural lighting, consistent
#     details, high visual quality, no text or watermark.
#
# so the subject shares a comma-clause with "Cinematic 16:9". A filter that
# split on commas dropped that clause whole and handed MMAudio nothing but
# boilerplate. Two real jobs shipped that way on 2026-09-05 and their audio had
# no relationship to the picture. These cases use the real shape.

WATERFALL = (
    "Cinematic 16:9 video of Waterfall. Clear subject motion, coherent "
    "environment, smooth camera movement, natural lighting, consistent details, "
    "high visual quality, no text or watermark., in 8k hyperrealistic cinematic "
    "look, ultra detailed textures, IMAX camera quality, natural depth of field"
)


def test_the_subject_survives_the_enhancer_template() -> None:
    """The one word that matters is the one the old filter deleted."""
    assert kaggle_worker.audio_prompt(WATERFALL) == "Waterfall"


def test_the_enhancer_boilerplate_is_not_handed_to_mmaudio() -> None:
    """ "High visual quality" is not a sound, and it was all the model got."""
    result = kaggle_worker.audio_prompt(WATERFALL).lower()

    for boilerplate in (
        "coherent environment",
        "consistent details",
        "high visual quality",
        "no text or watermark",
        "subject motion",
        "camera",
        "lighting",
    ):
        assert boilerplate not in result, boilerplate


def test_a_style_preset_keeps_its_setting_words_beside_the_subject() -> None:
    """A cyberpunk street still sounds like rain and a city."""
    composed = (
        "Cinematic 16:9 video of a street at night. Clear subject motion, coherent "
        "environment, smooth camera movement, natural lighting, consistent details, "
        "high visual quality, no text or watermark., in cyberpunk 2077 aesthetic, "
        "glowing neon lights, futuristic cityscape, rainy volumetric reflections, "
        "dark atmosphere"
    )

    result = kaggle_worker.audio_prompt(composed)

    assert result.startswith("a street at night")
    assert "futuristic cityscape" in result
    assert "rainy volumetric reflections" in result
    assert "aesthetic" not in result


def test_a_multi_word_subject_is_kept_whole() -> None:
    composed = (
        "Cinematic 9:16 video of A sheep walking in a farm. Clear subject motion, "
        "coherent environment, smooth camera movement, natural lighting, consistent "
        "details, high visual quality, no text or watermark."
    )

    assert kaggle_worker.audio_prompt(composed) == "A sheep walking in a farm"


def test_an_empty_prompt_stays_empty() -> None:
    assert kaggle_worker.audio_prompt("   ") == ""


def test_broadband_noise_is_no_longer_negative_prompted() -> None:
    """A waterfall, rain, wind and a river are all broadband noise.

    "static" and "hum" were added to suppress artefacts and suppressed the
    subject instead. What EXP-006 measured as valuable was the music and voice
    half of this list, which stays.
    """
    negative = kaggle_worker.AUDIO_NEGATIVE_PROMPT.lower()

    assert "static" not in negative
    assert "hum" not in negative
    for invented in ("music", "speech", "voice", "narration", "singing"):
        assert invented in negative


# --- loudness normalisation --------------------------------------------------
#
# MMAudio writes around -25 to -32 LUFS across four measured clips, against a
# -14 to -23 range for streaming and mobile. The first person to listen said
# they could barely hear it, and they were right. Normalising costs a re-encode
# of about 64 KB, which is nothing beside the picture it travels with.


def test_the_soundtrack_is_normalised_on_the_way_through(tmp_path: Path, monkeypatch) -> None:
    repo = _mmaudio_repo(tmp_path, monkeypatch)
    calls = _stub_subprocess(monkeypatch, repo, mux_succeeds=True)
    clip = tmp_path / "video.mp4"
    clip.write_bytes(SILENT_CLIP)

    assert kaggle_worker.add_audio(clip, "a paper dragon", 4) is True

    ffmpeg = _mux_call(calls)
    assert ffmpeg[ffmpeg.index("-c:a") + 1] == "aac"
    audio_filter = ffmpeg[ffmpeg.index("-filter:a") + 1]
    assert f"I={kaggle_worker.AUDIO_TARGET_LUFS}" in audio_filter
    # Second-pass values come from the first pass, so the gain is linear rather
    # than guessed frame by frame.
    assert "measured_I=-29.44" in audio_filter
    assert "linear=true" in audio_filter


def test_the_measurement_pass_runs_before_the_mux(tmp_path: Path, monkeypatch) -> None:
    """One pass would pump on a four-second clip; measuring first avoids it."""
    repo = _mmaudio_repo(tmp_path, monkeypatch)
    calls = _stub_subprocess(monkeypatch, repo, mux_succeeds=True)
    clip = tmp_path / "video.mp4"
    clip.write_bytes(SILENT_CLIP)

    kaggle_worker.add_audio(clip, "a paper dragon", 4)

    ffmpeg_calls = [argv for argv in calls if argv[0] == "ffmpeg"]
    assert _is_measurement(ffmpeg_calls[0])
    assert not _is_measurement(ffmpeg_calls[1])


def test_an_unreadable_measurement_still_ships_the_soundtrack(tmp_path: Path, monkeypatch) -> None:
    """Normalising is an enhancement on an enhancement.

    Losing the volume adjustment is acceptable; losing three minutes of GPU
    time over it is not.
    """
    repo = _mmaudio_repo(tmp_path, monkeypatch)
    calls = _stub_subprocess(monkeypatch, repo, mux_succeeds=True, measurement=None)
    clip = tmp_path / "video.mp4"
    clip.write_bytes(SILENT_CLIP)

    assert kaggle_worker.add_audio(clip, "a paper dragon", 4) is True

    assert clip.read_bytes() == MUXED_CLIP
    ffmpeg = _mux_call(calls)
    assert ffmpeg[ffmpeg.index("-c:a") + 1] == "copy"


def test_near_silence_is_left_alone_rather_than_amplified(tmp_path, monkeypatch) -> None:
    """Lifting a noise floor 30 dB produces hiss, not a soundtrack.

    Quiet is the better failure: it invites "the model found nothing here",
    which is true, rather than "the model produced static", which is worse than
    silence by EXP-006's own kill criterion.
    """
    monkeypatch.setattr(kaggle_worker, "_ffmpeg_executable", lambda: "ffmpeg")
    silent_json = MEASURED_JSON.replace('"input_i" : "-29.44"', '"input_i" : "-61.20"')

    class Completed:
        returncode = 0
        stdout = ""
        stderr = silent_json

    monkeypatch.setattr("subprocess.run", lambda *a, **k: Completed())

    assert kaggle_worker._measure_loudness(tmp_path / "clip.mp4") is None


def test_a_measurable_track_is_normalised(tmp_path, monkeypatch) -> None:
    """The floor must not be so high that ordinary MMAudio output trips it."""
    monkeypatch.setattr(kaggle_worker, "_ffmpeg_executable", lambda: "ffmpeg")

    class Completed:
        returncode = 0
        stdout = ""
        stderr = MEASURED_JSON

    monkeypatch.setattr("subprocess.run", lambda *a, **k: Completed())

    measured = kaggle_worker._measure_loudness(tmp_path / "clip.mp4")

    assert measured is not None
    assert measured["input_i"] == "-29.44"
    assert kaggle_worker.AUDIO_LOUDNESS_FLOOR_LUFS < -29.44 < kaggle_worker.AUDIO_TARGET_LUFS


def test_a_failed_measurement_command_is_not_fatal(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(kaggle_worker, "_ffmpeg_executable", lambda: "ffmpeg")

    def boom(*_a, **_k):
        raise OSError("ffmpeg vanished")

    monkeypatch.setattr("subprocess.run", boom)

    assert kaggle_worker._measure_loudness(tmp_path / "clip.mp4") is None


# A third prompt shape reaches the worker once Ollama is actually answering:
# the LLM writes one long sentence and trails camera, lighting and aspect-ratio
# clauses after commas, with no sentence break to separate them. This is the
# real output of `qwen3.5:2b` through the backend adapter on 2026-09-05.

LIVE_LLM = (
    "A high school girl with a confident stride walks purposefully down a sunlit "
    "suburban road lined with green trees and parked cars, captured in a "
    "cinematic wide shot with a slow push-in, soft natural lighting, 16:9 aspect ratio."
)


def test_a_live_llm_prompt_keeps_its_scene_and_drops_the_camera_work() -> None:
    result = kaggle_worker.audio_prompt(LIVE_LLM)

    assert result.startswith("A high school girl")
    assert "suburban road" in result
    for visual in ("wide shot", "push-in", "lighting", "aspect ratio"):
        assert visual not in result.lower(), visual


def test_the_first_clause_survives_whatever_shape_the_prompt_arrives_in() -> None:
    """The subject is never filtered, in any of the three shapes.

    Losing it is the failure that shipped two jobs with audio unrelated to the
    picture, and it happened because the filter had only ever been run against
    the one shape EXP-006's notebook used.
    """
    shapes = {
        "enhancer template": (WATERFALL, "Waterfall"),
        "live LLM": (LIVE_LLM, "A high school girl"),
        "raw notebook style": (
            "A red paper boat on a calm lake at sunrise, in 8k hyperrealistic cinematic look",
            "A red paper boat on a calm lake at sunrise",
        ),
    }

    for label, (prompt, expected_start) in shapes.items():
        assert kaggle_worker.audio_prompt(prompt).startswith(expected_start), label
