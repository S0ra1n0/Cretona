"""Thumbnails are signed against the bucket they were written to.

`SupabaseStorage.store_thumbnail` uploads into the **uploads** bucket, but
`to_response` signed the thumbnail with `video=True`, which looks in **videos**.
Signing found nothing, returned None, and the app rendered "Preview
unavailable" for every project that actually had a thumbnail.

547 tests missed it because `LocalStorage` serves both buckets from one
directory, so the local profile cannot express the difference. These tests
assert the flag directly instead.
"""

from __future__ import annotations

from typing import Any

from app.project_service import ProjectService


class RecordingStorage:
    """Records the bucket flag each media URL was requested with."""

    name = "supabase"

    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def read_url(self, path: str | None, base_url: str, *, video: bool = True) -> str | None:
        if path:
            self.calls.append((path, video))
        return f"https://signed/{path}" if path else None

    def flag_for(self, path: str) -> bool:
        return next(video for recorded, video in self.calls if recorded == path)


def response_for(row: dict[str, Any]) -> tuple[Any, RecordingStorage]:
    storage = RecordingStorage()
    service = ProjectService.__new__(ProjectService)
    service.storage = storage
    return service.to_response(row, "http://test"), storage


def project_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "p1",
        "owner_id": "u1",
        "title": "A clip",
        "prompt": "a paper boat",
        "image_path": "u1/ref.jpg",
        "video_path": "u1/p1/video.mp4",
        "thumbnail_path": "u1/p1/thumbnail.jpg",
        "provider": "kaggle",
        "status": "completed",
        "error_message": None,
        "progress_percent": 100,
        "step_message": None,
        "duration_seconds": 4,
        "aspect_ratio": "16:9",
        "created_at": "2026-09-01T06:38:25Z",
        "updated_at": "2026-09-01T14:11:39Z",
        "completed_at": "2026-09-01T14:11:39Z",
    }
    row.update(overrides)
    return row


def test_the_thumbnail_is_signed_against_the_uploads_bucket() -> None:
    """The regression. `video=True` here is the bug."""
    _, storage = response_for(project_row())

    assert storage.flag_for("u1/p1/thumbnail.jpg") is False


def test_the_video_is_still_signed_against_the_videos_bucket() -> None:
    _, storage = response_for(project_row())

    assert storage.flag_for("u1/p1/video.mp4") is True


def test_the_reference_image_stays_on_the_uploads_bucket() -> None:
    _, storage = response_for(project_row())

    assert storage.flag_for("u1/ref.jpg") is False


def test_a_project_with_a_thumbnail_reports_a_url() -> None:
    """What the app binds to. None here is what rendered "Preview unavailable"."""
    response, _ = response_for(project_row())

    assert response.thumbnail_url is not None


def test_no_thumbnail_means_no_url_and_no_signing_attempt() -> None:
    response, storage = response_for(project_row(thumbnail_path=None))

    assert response.thumbnail_url is None
    assert all(path != "u1/p1/thumbnail.jpg" for path, _ in storage.calls)
