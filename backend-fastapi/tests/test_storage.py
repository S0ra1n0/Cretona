from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.errors import AppError
from app.storage import (
    MAX_IMAGE_BYTES,
    LocalStorage,
    SupabaseStorage,
    assert_owns_path,
    upload_path,
    video_path,
)
from tests.conftest import USER_A, USER_B

SERVICE_KEY = "test-service-role-key-not-a-real-one"
PROJECT_URL = "https://project-ref.supabase.co"


# --- path scoping and ownership ---------------------------------------------


def test_object_keys_are_scoped_to_the_owner() -> None:
    assert upload_path(USER_A, "image/png").startswith(f"{USER_A}/")
    assert upload_path(USER_A, "image/png").endswith(".png")
    assert video_path(USER_A, "p1") == f"{USER_A}/p1/video.mp4"


def test_unknown_content_type_falls_back_to_a_neutral_extension() -> None:
    assert upload_path(USER_A, "application/x-thing").endswith(".bin")


@pytest.mark.parametrize(
    "path",
    ["", f"{USER_B}/2026-01-01/x.png", "../etc/passwd", f"not-{USER_A}/x.png"],
)
def test_paths_owned_by_someone_else_are_refused(path: str) -> None:
    with pytest.raises(AppError) as caught:
        assert_owns_path(USER_A, path)

    assert caught.value.status_code == 403
    assert caught.value.code == "FORBIDDEN"


def test_own_path_is_accepted() -> None:
    assert_owns_path(USER_A, f"{USER_A}/2026-01-01/x.png")


def test_cannot_attach_another_users_image_to_a_project(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/projects",
        headers=user_headers,
        json={"imagePath": f"{USER_B}/2026-01-01/stolen.png"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- signed uploads ---------------------------------------------------------


def test_signed_upload_is_scoped_and_expiring(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/uploads/sign",
        headers=user_headers,
        json={"contentType": "image/png", "sizeBytes": 1024},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["storagePath"].startswith(f"{USER_A}/")
    assert body["expiresAt"].endswith("Z")
    assert body["uploadUrl"]


@pytest.mark.parametrize("content_type", ["application/pdf", "text/html", "image/gif"])
def test_unsupported_image_type_is_rejected(
    client: TestClient,
    user_headers: dict[str, str],
    content_type: str,
) -> None:
    response = client.post(
        "/api/v1/uploads/sign",
        headers=user_headers,
        json={"contentType": content_type, "sizeBytes": 1024},
    )

    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["issue"] == "unsupported_type"


def test_oversized_image_is_rejected(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/uploads/sign",
        headers=user_headers,
        json={"contentType": "image/png", "sizeBytes": MAX_IMAGE_BYTES + 1},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_signing_requires_authentication(supabase_client: TestClient) -> None:
    response = supabase_client.post(
        "/api/v1/uploads/sign",
        json={"contentType": "image/png", "sizeBytes": 1024},
    )

    assert response.status_code == 401


# --- local backend ----------------------------------------------------------


def test_local_url_mapping_is_server_relative(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)

    assert storage.read_url(None, "http://api") is None
    assert storage.read_url("/media/a.mp4", "http://api") == "http://api/media/a.mp4"
    # An absolute URL is passed through rather than double-prefixed.
    assert storage.read_url("https://cdn/x.mp4", "http://api") == "https://cdn/x.mp4"


def test_local_remove_refuses_to_escape_the_media_directory(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    outsider = tmp_path / "important.txt"
    outsider.write_text("do not delete", encoding="utf-8")

    LocalStorage(media).remove_objects("../important.txt", None)

    assert outsider.exists()


def test_deleting_a_project_removes_its_stored_video(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    created = client.post(
        "/api/v1/projects",
        headers=user_headers,
        json={"prompt": "a lantern drifting", "provider": "fake"},
    ).json()
    client.get(f"/api/v1/projects/{created['id']}", headers=user_headers)
    completed = client.get(f"/api/v1/projects/{created['id']}", headers=user_headers).json()
    assert completed["status"] == "completed"

    video = httpx.URL(completed["videoUrl"]).path
    assert client.get(video).status_code == 200

    deleted = client.delete(f"/api/v1/projects/{created['id']}", headers=user_headers)
    assert deleted.status_code == 204

    # Storage costs money and the user asked for it to be gone.
    assert client.get(video).status_code == 404


# --- supabase backend, against a mock transport -----------------------------


def build_storage(handler: Any, ttl: int = 3600) -> SupabaseStorage:
    return SupabaseStorage(
        base_url=PROJECT_URL,
        service_role_key=SERVICE_KEY,
        uploads_bucket="uploads",
        videos_bucket="videos",
        signed_url_ttl_seconds=ttl,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_signed_read_url_is_bounded_and_bucket_scoped() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"signedURL": "/object/sign/videos/k?token=abc"})

    url = build_storage(handler, ttl=900).read_url(f"{USER_A}/p1/video.mp4", "http://api")

    assert seen["url"] == f"{PROJECT_URL}/storage/v1/object/sign/videos/{USER_A}/p1/video.mp4"
    # Bounded: the TTL is sent explicitly, never omitted.
    assert seen["body"] == {"expiresIn": 900}
    assert seen["auth"] == f"Bearer {SERVICE_KEY}"
    assert url == f"{PROJECT_URL}/storage/v1/object/sign/videos/k?token=abc"


def test_image_urls_are_signed_against_the_uploads_bucket() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"signedURL": "/object/sign/uploads/k?token=abc"})

    build_storage(handler).read_url(f"{USER_A}/img.png", "http://api", video=False)

    assert "/object/sign/uploads/" in seen["url"]


def test_missing_object_yields_no_url_rather_than_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "Object not found", "bucket": "videos"})

    assert build_storage(handler).read_url(f"{USER_A}/p1/video.mp4", "http://api") is None


def test_signed_upload_request_is_scoped_to_the_caller() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"url": "/object/upload/sign/uploads/k?token=t", "token": "t"},
        )

    signed = build_storage(handler).create_signed_upload(USER_A, "image/png", 2048, "http://api")

    assert f"/object/upload/sign/uploads/{USER_A}/" in seen["url"]
    assert signed.storage_path.startswith(f"{USER_A}/")
    assert signed.token == "t"
    assert signed.upload_url.startswith(f"{PROJECT_URL}/storage/v1/")


def test_upload_signing_failure_does_not_leak_upstream_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={"message": "bucket 'uploads' misconfigured", "key": "sk_x"},
        )

    with pytest.raises(AppError) as caught:
        build_storage(handler).create_signed_upload(USER_A, "image/png", 2048, "http://api")

    assert caught.value.status_code == 500
    assert "bucket" not in caught.value.message
    assert "sk_x" not in caught.value.message


def test_rehosting_downloads_then_uploads_to_an_owned_key() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        if request.method == "GET":
            return httpx.Response(
                200,
                content=b"video-bytes",
                headers={"content-type": "video/mp4"},
            )
        assert request.content == b"video-bytes"
        return httpx.Response(200, json={"Key": "videos/x"})

    stored = build_storage(handler).store_video(USER_A, "p1", "https://provider.example/out.mp4")

    assert stored == f"{USER_A}/p1/video.mp4"
    assert calls[0][0] == "GET"
    assert calls[1][1] == f"{PROJECT_URL}/storage/v1/object/videos/{USER_A}/p1/video.mp4"


def test_rehosting_a_failed_download_is_a_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with pytest.raises(AppError) as caught:
        build_storage(handler).store_video(USER_A, "p1", "https://provider.example/gone.mp4")

    assert caught.value.status_code == 502
    assert caught.value.code == "PROVIDER_ERROR"


def test_rehosting_a_failed_upload_does_not_leak_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=b"bytes")
        return httpx.Response(500, json={"message": "quota exceeded on bucket videos"})

    with pytest.raises(AppError) as caught:
        build_storage(handler).store_video(USER_A, "p1", "https://provider.example/out.mp4")

    assert caught.value.status_code == 500
    assert "quota" not in caught.value.message


def test_object_removal_is_best_effort() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("storage unreachable")

    # Must not raise: a cleanup failure cannot block deleting the project.
    build_storage(handler).remove_objects(f"{USER_A}/img.png", f"{USER_A}/p1/video.mp4")


def test_removal_targets_both_buckets() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={})

    build_storage(handler).remove_objects(f"{USER_A}/img.png", f"{USER_A}/p1/video.mp4")

    assert seen == [
        f"{PROJECT_URL}/storage/v1/object/uploads",
        f"{PROJECT_URL}/storage/v1/object/videos",
    ]


# --- configuration ----------------------------------------------------------


def test_supabase_storage_requires_credentials() -> None:
    with pytest.raises(ValidationError, match="CRETONA_SUPABASE_URL is required"):
        Settings(storage_backend="supabase")

    with pytest.raises(ValidationError, match="SERVICE_ROLE_KEY is required"):
        Settings(storage_backend="supabase", supabase_url=PROJECT_URL)


def test_service_role_key_is_not_exposed_by_repr() -> None:
    settings = Settings(
        storage_backend="supabase",
        supabase_url=PROJECT_URL,
        supabase_service_role_key="super-secret-service-key",
    )

    assert "super-secret-service-key" not in repr(settings)


@pytest.mark.parametrize("ttl", [59, 604801])
def test_signed_url_ttl_is_bounded(ttl: int) -> None:
    with pytest.raises(ValidationError):
        Settings(signed_url_ttl_seconds=ttl)
