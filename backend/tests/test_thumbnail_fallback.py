"""An image-to-video project uses its reference image as the gallery preview.

Wan2.1 is text-only, so image-to-video runs on the still-plus-motion tiers.
Those had no thumbnail of their own and every card read "Preview unavailable"
while the uploaded picture sat in Storage unused. `_thumbnail` now falls back to
that picture when frame extraction produces nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.project_service import ProjectService

IMAGE = b"\xff\xd8\xff\xe0 pretend jpeg bytes"


class SupabaseLikeStorage:
    """Has `store_thumbnail`, so the bytes are uploaded rather than written."""

    name = "supabase"

    def __init__(self, image: bytes | None = IMAGE) -> None:
        self.image = image
        self.stored: bytes | None = None

    def read_image_bytes(self, path: str | None) -> bytes | None:
        return self.image if path else None

    def store_thumbnail_path(self, user_id: str, project_id: str) -> str:
        return f"{user_id}/{project_id}/thumbnail.jpg"

    def store_thumbnail(self, user_id: str, project_id: str, content: bytes) -> str:
        self.stored = content
        return f"{user_id}/{project_id}/thumbnail.jpg"


class LocalLikeStorage:
    """No `store_thumbnail`, so the bytes land on disk under the media dir."""

    name = "local"

    def __init__(self, root: Path, image: bytes | None = IMAGE) -> None:
        self.root = root
        self.image = image

    def read_image_bytes(self, path: str | None) -> bytes | None:
        return self.image if path else None

    def store_thumbnail_path(self, user_id: str, project_id: str) -> str:
        return f"/media/{user_id}/{project_id}/thumbnail.jpg"

    def local_video_path(self, stored_path: str) -> Path | None:
        return self.root / stored_path.lstrip("/")


def service_for(storage: Any) -> ProjectService:
    service = ProjectService.__new__(ProjectService)
    service.storage = storage
    return service


def row(**overrides: Any) -> dict[str, Any]:
    base = {"id": "project-1", "image_path": "user-1/reference.jpg"}
    base.update(overrides)
    return base


def test_the_reference_image_is_uploaded_as_the_thumbnail() -> None:
    storage = SupabaseLikeStorage()

    result = service_for(storage)._thumbnail_from_reference(row(), "user-1")

    assert result == "user-1/project-1/thumbnail.jpg"
    # The original bytes, not a re-encode: the server has no image library.
    assert storage.stored == IMAGE


def test_the_reference_image_is_written_for_the_local_backend(tmp_path: Path) -> None:
    storage = LocalLikeStorage(tmp_path)

    result = service_for(storage)._thumbnail_from_reference(row(), "user-1")

    assert result == "/media/user-1/project-1/thumbnail.jpg"
    written = tmp_path / "media/user-1/project-1/thumbnail.jpg"
    assert written.read_bytes() == IMAGE


def test_a_text_only_project_has_nothing_to_fall_back_to() -> None:
    storage = SupabaseLikeStorage()

    assert service_for(storage)._thumbnail_from_reference(row(image_path=None), "user-1") is None
    assert storage.stored is None


def test_an_unreadable_reference_image_is_not_a_failure() -> None:
    """A preview must never fail a finished video."""
    storage = SupabaseLikeStorage(image=None)

    assert service_for(storage)._thumbnail_from_reference(row(), "user-1") is None


def test_frame_extraction_still_wins_when_it_produces_a_thumbnail() -> None:
    """The video's own frame is the better preview; the image is the fallback."""
    storage = SupabaseLikeStorage()
    service = service_for(storage)
    service._thumbnail_from_video = lambda *_args: "user-1/project-1/from-video.jpg"  # type: ignore[method-assign]

    assert service._thumbnail(row(), "user-1", "user-1/project-1/video.mp4") == (
        "user-1/project-1/from-video.jpg"
    )
    assert storage.stored is None


def test_the_image_is_used_once_extraction_comes_back_empty() -> None:
    storage = SupabaseLikeStorage()
    service = service_for(storage)
    service._thumbnail_from_video = lambda *_args: None  # type: ignore[method-assign]

    assert service._thumbnail(row(), "user-1", "user-1/project-1/video.mp4") == (
        "user-1/project-1/thumbnail.jpg"
    )
    assert storage.stored == IMAGE
