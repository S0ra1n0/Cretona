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

    def store_image(self, user_id: str, content_type: str, data: bytes) -> str: ...

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

    def store_image(self, user_id: str, content_type: str, data: bytes) -> str:
        validate_upload_request(content_type, len(data))
        path = upload_path(user_id, content_type)
        destination = self.media_dir / "uploads" / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return path

    def read_url(self, path: str | None, base_url: str, *, video: bool = True) -> str | None:
        del video
        if not path:
            return None
        if path.startswith(("http://", "https://")):
            return path
        clean = path.lstrip("/")
        if clean.startswith("media/"):
            return f"{base_url.rstrip('/')}/{clean}"
        if (self.media_dir / "uploads" / clean).exists():
            return f"{base_url.rstrip('/')}/media/uploads/{clean}"
        return f"{base_url.rstrip('/')}/media/{clean}"

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
        if (
            candidate != media_root
            and (media_root in candidate.parents or candidate == media_root)
            and candidate.exists()
        ):
            return candidate

        uploads_candidate = (self.media_dir / "uploads" / relative).resolve()
        if (
            uploads_candidate != media_root
            and (media_root in uploads_candidate.parents)
            and uploads_candidate.exists()
        ):
            return uploads_candidate

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
        media_dir: Path | None = None,
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
        # Optional: lets store_video read fake-provider local files by resolving
        # the /media/<name> URL prefix to an actual on-disk path.
        self._media_dir: Path | None = media_dir

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
        """Resolve a local video path if media_dir is available.

        Allows thumbnail extraction when running with local/fake provider media
        or a mounted media_dir (B-12).
        """
        if self._media_dir is not None and stored_path:
            if stored_path.startswith("/media/"):
                candidate = self._media_dir / stored_path[len("/media/") :]
            else:
                candidate = self._media_dir / stored_path
            if candidate.is_file():
                return candidate
            fallback = self._media_dir / Path(stored_path).name
            if fallback.is_file():
                return fallback
        return None

    def store_thumbnail_path(self, user_id: str, project_id: str) -> str:
        return f"{user_id}/{project_id}/thumbnail.jpg"

    def store_thumbnail(self, user_id: str, project_id: str, content: bytes) -> str:
        """Upload a generated thumbnail image frame into Supabase Storage."""
        path = self.store_thumbnail_path(user_id, project_id)
        upload = self._client.post(
            f"{self.api}/object/{self.uploads_bucket}/{path}",
            headers={
                **self._headers,
                "Content-Type": "image/jpeg",
                "x-upsert": "true",
            },
            content=content,
        )
        if upload.status_code >= 400:
            return ""
        return path

    def store_image(self, user_id: str, content_type: str, data: bytes) -> str:
        validate_upload_request(content_type, len(data))
        path = upload_path(user_id, content_type)
        upload = self._client.post(
            f"{self.api}/object/{self.uploads_bucket}/{path}",
            headers={
                **self._headers,
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            content=data,
        )
        if upload.status_code >= 400:
            raise AppError(500, "INTERNAL_ERROR", "Could not store the uploaded image.")
        return path

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

        ``source`` is one of:
        - An HTTP/HTTPS URL (real provider) — fetched via the httpx client.
        - A ``/media/<name>`` URL path (fake provider with Supabase storage) —
          resolved to ``media_dir/<name>`` on disk when ``media_dir`` is set.
        - Any other local path — read directly from disk as a fallback.
        """
        if source.startswith(("http://", "https://")):
            try:
                download = self._client.get(source)
            except httpx.RequestError as exc:
                raise AppError(
                    502,
                    "PROVIDER_ERROR",
                    "Could not reach the provider result URL.",
                ) from exc
            if download.status_code >= 400:
                raise AppError(
                    502,
                    "PROVIDER_ERROR",
                    f"Could not download the result ({download.status_code}).",
                )
            video_bytes = download.content
            content_type = download.headers.get("content-type", "video/mp4")
        else:
            # Local path: fake or deterministic provider running with Supabase
            # storage backend.  Resolve the /media/<name> URL prefix used by
            # the local StaticFiles mount to an actual filesystem path via
            # media_dir, then read the bytes directly from disk.
            if source.startswith("/media/") and self._media_dir is not None:
                local = self._media_dir / source[len("/media/") :]
            else:
                local = Path(source)
            if not local.is_file():
                raise AppError(
                    502,
                    "PROVIDER_ERROR",
                    "Provider result file not found on disk.",
                )
            video_bytes = local.read_bytes()
            content_type = "video/mp4"

        path = video_path(user_id, project_id)
        upload = self._client.post(
            f"{self.api}/object/{self.videos_bucket}/{path}",
            headers={
                **self._headers,
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            content=video_bytes,
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
