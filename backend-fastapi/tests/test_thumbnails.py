from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage import LocalStorage, SupabaseStorage
from app.thumbnails import ThumbnailGenerator
from tests.conftest import USER_A

HEADERS = {"X-Debug-User-Id": USER_A}


def build(**overrides: object) -> ThumbnailGenerator:
    settings: dict = {"ffmpeg_path": "ffmpeg", "enabled": True, "seek_seconds": 1.0}
    settings.update(overrides)
    return ThumbnailGenerator(**settings)  # type: ignore[arg-type]


# --- command ----------------------------------------------------------------


def test_command_seeks_before_the_input() -> None:
    command = build(seek_seconds=2.5).build_command(Path("in.mp4"), Path("out.jpg"))

    # -ss before -i is the fast path: it decodes from the nearest keyframe
    # rather than walking the whole file.
    assert command.index("-ss") < command.index("-i")
    assert command[command.index("-ss") + 1] == "2.5"


def test_command_asks_for_exactly_one_frame() -> None:
    command = build().build_command(Path("in.mp4"), Path("out.jpg"))

    assert command[command.index("-frames:v") + 1] == "1"
    assert command[-1] == "out.jpg"
    # Never interactive: a prompt would hang the poller thread forever.
    assert "-nostdin" in command


# --- availability -----------------------------------------------------------


def test_a_disabled_generator_is_unavailable() -> None:
    assert build(enabled=False).available() is False


def test_a_missing_binary_is_unavailable() -> None:
    assert build(ffmpeg_path="definitely-not-a-real-binary-xyz").available() is False


def test_extract_declines_when_unavailable(tmp_path: Path) -> None:
    assert (
        build(ffmpeg_path="definitely-not-a-real-binary-xyz").extract(
            tmp_path / "in.mp4", tmp_path / "out.jpg"
        )
        is False
    )


# --- failure handling -------------------------------------------------------


def test_a_nonzero_exit_is_a_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    generator = build()
    monkeypatch.setattr(generator, "available", lambda: True)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, returncode=1, stdout=b"", stderr=b""),
    )

    assert generator.extract(tmp_path / "in.mp4", tmp_path / "out.jpg") is False


def test_a_zero_exit_with_no_file_is_still_a_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = build()
    monkeypatch.setattr(generator, "available", lambda: True)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, returncode=0, stdout=b"", stderr=b""),
    )

    # A video shorter than the seek offset yields no frame despite exit 0.
    assert generator.extract(tmp_path / "in.mp4", tmp_path / "out.jpg") is False


def test_a_timeout_is_swallowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    generator = build()
    monkeypatch.setattr(generator, "available", lambda: True)

    def explode(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=20)

    monkeypatch.setattr(subprocess, "run", explode)

    assert generator.extract(tmp_path / "in.mp4", tmp_path / "out.jpg") is False


def test_a_written_file_is_a_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    generator = build()
    target = tmp_path / "out.jpg"
    monkeypatch.setattr(generator, "available", lambda: True)

    def write(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
        target.write_bytes(b"jpeg-bytes")
        return subprocess.CompletedProcess(args, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", write)

    assert generator.extract(tmp_path / "in.mp4", target) is True


# --- storage integration ----------------------------------------------------


def test_local_storage_exposes_a_real_file_path(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    (tmp_path / "u" / "p").mkdir(parents=True)
    (tmp_path / "u" / "p" / "video.mp4").write_bytes(b"x")

    resolved = storage.local_video_path("/media/u/p/video.mp4")

    assert resolved is not None
    assert resolved.exists()


def test_bucket_storage_has_no_local_path() -> None:
    storage = SupabaseStorage(
        base_url="https://x.supabase.co",
        service_role_key="k",
        uploads_bucket="uploads",
        videos_bucket="videos",
        signed_url_ttl_seconds=3600,
    )

    # Honest None rather than a path that does not exist: thumbnailing a bucket
    # object would need a download round trip.
    assert storage.local_video_path("u/p/video.mp4") is None


def test_completion_succeeds_without_ffmpeg(client: TestClient) -> None:
    created = client.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "no ffmpeg here"}
    ).json()
    client.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)
    body = client.get(f"/api/v1/projects/{created['id']}", headers=HEADERS).json()

    # thumbnailUrl is nullable by contract, so a missing binary costs a
    # thumbnail rather than the whole generation.
    assert body["status"] == "completed"
    assert body["videoUrl"]
    assert body["thumbnailUrl"] is None


def test_a_generated_thumbnail_is_returned(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = client.app.state.project_service
    monkeypatch.setattr(service.thumbnails, "available", lambda: True)

    def write(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        Path(command[-1]).write_bytes(b"jpeg-bytes")
        return subprocess.CompletedProcess(command, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", write)

    created = client.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "with a still"}
    ).json()
    client.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)
    body = client.get(f"/api/v1/projects/{created['id']}", headers=HEADERS).json()

    assert body["thumbnailUrl"].endswith(f"/media/{USER_A}/{created['id']}/thumbnail.jpg")
    assert client.get(f"/media/{USER_A}/{created['id']}/thumbnail.jpg").content == b"jpeg-bytes"
