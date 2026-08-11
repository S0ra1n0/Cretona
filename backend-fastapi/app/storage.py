from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx

from app.errors import AppError

ALLOWED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_IMAGE_BYTES = 10 * 1024 * 1024

EXTENSION = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


@dataclass(frozen=True)
class SignedUpload:
    upload_url: str
    storage_path: str
    token: str
    expires_at: str


# --- path rules -------------------------------------------------------------
#
# Object keys embed the owner as the first segment. That is what lets Storage
# policies authorize on the path prefix, and what makes ownership checkable
# without a database round trip (SECURITY.md 4).


def upload_path(user_id: str, content_type: str) -> str:
    extension = EXTENSION.get(content_type, "bin")
    day = datetime.now(UTC).date().isoformat()
    return f"{user_id}/{day}/{uuid4()}.{extension}"


def video_path(user_id: str, project_id: str) -> str:
    return f"{user_id}/{project_id}/video.mp4"


def assert_owns_path(user_id: str, path: str) -> None:
    """Reject a path whose owner segment is not the caller.

    Without this a user could attach someone else's uploaded image to their own
    project simply by passing its path.
    """
    if not path or path.split("/")[0] != user_id:
        raise AppError(403, "FORBIDDEN", "That file does not belong to you.")


def validate_upload_request(content_type: str, size_bytes: int) -> None:
    """Backend-independent input rules, checked before any network call."""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise AppError(
            400,
            "VALIDATION_ERROR",
            "That image type is not supported.",
            [{"field": "body.contentType", "issue": "unsupported_type"}],
        )
    if size_bytes > MAX_IMAGE_BYTES:
        raise AppError(413, "PAYLOAD_TOO_LARGE", "Images must be 10 MB or smaller.")


class StorageBackend(Protocol):
    """What the service needs from media storage.

    Android never sees any of this: it receives whatever `read_url` returns and
    cannot tell a local file mount from a signed Supabase URL.
    """

    name: str

    def create_signed_upload(
        self, user_id: str, content_type: str, size_bytes: int, base_url: str
    ) -> SignedUpload: ...

    def read_url(self, path: str | None, base_url: str, *, video: bool = True) -> str | None: ...

    def store_video(self, user_id: str, project_id: str, source: str) -> str: ...

    def remove_objects(self, image_path: str | None, video_path: str | None) -> None: ...

    def local_video_path(self, stored_path: str) -> Path | None:
        """Where the stored video lives on disk, if anywhere.

        Thumbnail extraction needs a real file. A backend that keeps bytes in a
        bucket returns None rather than pretending otherwise.
        """
        ...


class LocalStorage:
    """Filesystem-backed storage for the credential-free local profile.

    Exercises the same contract as Supabase without network access or a bucket,
    so the whole media path stays testable on a machine with no credentials.
    """

    name = "local"

    def __init__(self, media_dir: Path) -> None:
        self.media_dir = media_dir

    def create_signed_upload(
        self, user_id: str, content_type: str, size_bytes: int, base_url: str
    ) -> SignedUpload:
        validate_upload_request(content_type, size_bytes)
        path = upload_path(user_id, content_type)
        expires_at = datetime.now(UTC) + timedelta(hours=2)
        return SignedUpload(
            upload_url=f"{base_url.rstrip('/')}/media/uploads/{path}",
            storage_path=path,
            # Not a credential. The local profile has nothing to authenticate
            # against, and this value is never accepted as proof of anything.
            token="local-development-upload",
            expires_at=expires_at.isoformat().replace("+00:00", "Z"),
        )

    def read_url(self, path: str | None, base_url: str, *, video: bool = True) -> str | None:
        del video
        if not path:
            return None
        if path.startswith(("http://", "https://")):
            return path
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    def local_video_path(self, stored_path: str) -> Path | None:
        return self._resolve(stored_path)

    def store_thumbnail_path(self, user_id: str, project_id: str) -> str:
        return f"/media/{user_id}/{project_id}/thumbnail.jpg"

    def store_video(self, user_id: str, project_id: str, source: str) -> str:
        # The local fake provider already writes into the media directory, so
        # re-hosting is a copy rather than a download.
        destination = self.media_dir / user_id / project_id
        destination.mkdir(parents=True, exist_ok=True)
        source_file = self.media_dir / Path(source.lstrip("/")).name
        target = destination / "video.mp4"
        if source_file.exists():
            shutil.copyfile(source_file, target)
        else:
            target.write_bytes(b"")
        return f"/media/{user_id}/{project_id}/video.mp4"

    def remove_objects(self, image_path: str | None, video_path: str | None) -> None:
        """Best-effort cleanup; a failure must not block deleting the project."""
        for path in (image_path, video_path):
            candidate = self._resolve(path)
            if candidate is None:
                continue
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                continue

    def _resolve(self, path: str | None) -> Path | None:
        """Map a stored path onto a file inside the media directory, or None.

        Anything that escapes the media directory is refused rather than
        deleted: a traversal in a stored path must not turn into an arbitrary
        file removal.
        """
        if not path or path.startswith(("http://", "https://")):
            return None

        relative = path.lstrip("/").removeprefix("media/")
        candidate = (self.media_dir / relative).resolve()
        media_root = self.media_dir.resolve()
        if candidate == media_root or media_root not in candidate.parents:
            return None
        return candidate


class SupabaseStorage:
    """Supabase Storage over its REST API.

    Uses the service-role key, which bypasses RLS, so every path is checked
    against the caller in code. Storage policies are the second line of
    defence, not the first.
    """

    name = "supabase"

    def __init__(
        self,
        *,
        base_url: str,
        service_role_key: str,
        uploads_bucket: str,
        videos_bucket: str,
        signed_url_ttl_seconds: int,
        client: httpx.Client | None = None,
    ) -> None:
        self.api = f"{base_url.rstrip('/')}/storage/v1"
        self.uploads_bucket = uploads_bucket
        self.videos_bucket = videos_bucket
        self.signed_url_ttl_seconds = signed_url_ttl_seconds
        self._client = client or httpx.Client(timeout=30)
        self._headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
        }

    def create_signed_upload(
        self, user_id: str, content_type: str, size_bytes: int, base_url: str
    ) -> SignedUpload:
        del base_url
        validate_upload_request(content_type, size_bytes)
        path = upload_path(user_id, content_type)

        response = self._client.post(
            f"{self.api}/object/upload/sign/{self.uploads_bucket}/{path}",
            headers=self._headers,
        )
        if response.status_code >= 400:
            # The upstream body may name buckets or keys, so it is not relayed.
            raise AppError(500, "INTERNAL_ERROR", "Could not prepare the upload.")

        body = response.json()
        signed = body.get("url") or body.get("signedUrl") or ""
        expires_at = datetime.now(UTC) + timedelta(hours=2)
        return SignedUpload(
            upload_url=self._absolute(signed),
            storage_path=path,
            token=body.get("token", ""),
            expires_at=expires_at.isoformat().replace("+00:00", "Z"),
        )

    def local_video_path(self, stored_path: str) -> Path | None:
        # Bytes live in a bucket. Generating a thumbnail here would need a
        # download round trip, which is not implemented.
        del stored_path
        return None

    def read_url(self, path: str | None, base_url: str, *, video: bool = True) -> str | None:
        """Mint a short-lived read URL.

        Signed URLs are minted per response and never persisted: they expire,
        so a stored URL is a guaranteed-stale link.
        """
        del base_url
        if not path:
            return None
        if path.startswith(("http://", "https://")):
            return path

        bucket = self.videos_bucket if video else self.uploads_bucket
        response = self._client.post(
            f"{self.api}/object/sign/{bucket}/{path}",
            headers=self._headers,
            json={"expiresIn": self.signed_url_ttl_seconds},
        )
        if response.status_code >= 400:
            # A missing object is not an error the caller can act on; the field
            # is simply absent, exactly as the Express reference behaves.
            return None

        signed = response.json().get("signedURL") or response.json().get("signedUrl") or ""
        return self._absolute(signed) if signed else None

    def store_video(self, user_id: str, project_id: str, source: str) -> str:
        """Re-host a provider result.

        Provider URLs expire, so persisting one guarantees a broken link within
        days. The bytes are copied into our own bucket before the project is
        marked completed.
        """
        download = self._client.get(source)
        if download.status_code >= 400:
            raise AppError(
                502,
                "PROVIDER_ERROR",
                f"Could not download the result ({download.status_code}).",
            )

        path = video_path(user_id, project_id)
        upload = self._client.post(
            f"{self.api}/object/{self.videos_bucket}/{path}",
            headers={
                **self._headers,
                "Content-Type": download.headers.get("content-type", "video/mp4"),
                "x-upsert": "true",
            },
            content=download.content,
        )
        if upload.status_code >= 400:
            raise AppError(500, "INTERNAL_ERROR", "Could not store the generated video.")
        return path

    def remove_objects(self, image_path: str | None, video_path: str | None) -> None:
        """Best-effort cleanup; a failure must not block deleting the project."""
        for bucket, path in ((self.uploads_bucket, image_path), (self.videos_bucket, video_path)):
            if not path or path.startswith(("http://", "https://")):
                continue
            try:
                self._client.request(
                    "DELETE",
                    f"{self.api}/object/{bucket}",
                    headers=self._headers,
                    json={"prefixes": [path]},
                )
            except httpx.HTTPError:
                continue

    def _absolute(self, signed: str) -> str:
        if signed.startswith(("http://", "https://")):
            return signed
        return f"{self.api}/{signed.lstrip('/')}"
