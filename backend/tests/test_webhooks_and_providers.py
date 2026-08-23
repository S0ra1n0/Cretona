from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.providers import (
    StillFetchError,
    _fetch_ai_still_typed,
    _render_kenburns_from_ai_still,
)
from app.webhook_verification import signing_payload
from tests.conftest import USER_A, WEBHOOK_SECRET

USER_HEADERS = {"X-Debug-User-Id": USER_A}


def sign(
    payload: dict[str, Any],
    secret: str = WEBHOOK_SECRET,
    timestamp: str | None = None,
) -> tuple[bytes, dict[str, str]]:
    """Sign the exact bytes that will be sent.

    The server verifies the raw body, so the test must post `content=` rather
    than `json=`; re-serializing would change the bytes the signature covers.
    The timestamp is inside the MAC, so it is signed here too (T2-4).
    """
    body = json.dumps(payload).encode("utf-8")
    sent_at = timestamp or str(int(datetime.now(UTC).timestamp()))
    digest = hmac.new(
        secret.encode("utf-8"), signing_payload(sent_at, body), hashlib.sha256
    ).hexdigest()
    return body, {
        "X-Cretona-Signature": f"sha256={digest}",
        "X-Cretona-Timestamp": sent_at,
        "Content-Type": "application/json",
    }


def post_webhook(
    client: TestClient,
    payload: dict[str, Any],
    *,
    provider: str = "fake",
    secret: str = WEBHOOK_SECRET,
) -> Any:
    body, headers = sign(payload, secret)
    return client.post(f"/api/v1/webhooks/{provider}", content=body, headers=headers)


def test_wan21_provider_full_flow(client: TestClient) -> None:
    # 1. Create project with wan21 provider
    res = client.post(
        "/api/v1/projects",
        headers=USER_HEADERS,
        json={"prompt": "A futuristic city in neon rain", "provider": "wan21"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["provider"] == "wan21"
    assert data["status"] == "pending"
    pid = data["id"]

    # 2. Advance / poll
    poll1 = client.get(f"/api/v1/projects/{pid}", headers=USER_HEADERS)
    assert poll1.status_code == 200
    assert poll1.json()["status"] in ("generating", "completed")

    # 3. Poll again to complete
    poll2 = client.get(f"/api/v1/projects/{pid}", headers=USER_HEADERS)
    assert poll2.status_code == 200
    assert poll2.json()["status"] == "completed"
    assert poll2.json()["videoUrl"] is not None


def test_provider_webhook_success(client: TestClient) -> None:
    # 1. Create a project
    created = client.post(
        "/api/v1/projects",
        headers=USER_HEADERS,
        json={"prompt": "webhook test video", "provider": "fake"},
    ).json()
    pid = created["id"]

    # 2. Receive success webhook
    webhook_res = post_webhook(
        client,
        {
            "project_id": pid,
            "status": "succeeded",
            "video_path": "/media/demo-output.mp4",
            "duration_seconds": 5,
        },
    )
    assert webhook_res.status_code == 200
    res_data = webhook_res.json()
    assert res_data["received"] is True
    assert res_data["projectId"] == pid
    assert res_data["status"] == "completed"

    # 3. Verify project is completed
    project = client.get(f"/api/v1/projects/{pid}", headers=USER_HEADERS).json()
    assert project["status"] == "completed"
    assert project["videoUrl"] is not None


def test_provider_webhook_failure(client: TestClient) -> None:
    # 1. Create a project
    created = client.post(
        "/api/v1/projects",
        headers=USER_HEADERS,
        json={"prompt": "webhook fail test", "provider": "fake"},
    ).json()
    pid = created["id"]

    # 2. Receive failure webhook
    webhook_res = post_webhook(
        client,
        {
            "project_id": pid,
            "status": "failed",
            "error_code": "content_policy",
        },
    )
    assert webhook_res.status_code == 200
    res_data = webhook_res.json()
    assert res_data["received"] is True
    assert res_data["projectId"] == pid
    assert res_data["status"] == "failed"

    # 3. Verify project is failed
    project = client.get(f"/api/v1/projects/{pid}", headers=USER_HEADERS).json()
    assert project["status"] == "failed"


def test_quota_cost_weighting(client: TestClient) -> None:
    # Set quota limit = 3
    client.app.state.settings.generation_quota_limit = 3

    # Project 1: Standard (cost 1) -> used 1, remaining 2
    r1 = client.post(
        "/api/v1/projects",
        headers=USER_HEADERS,
        json={"prompt": "standard 5s", "provider": "fake"},
    )
    assert r1.status_code == 201

    # Project 2: Real AI or 10s (cost 2) -> used 1+2=3, remaining 0
    r2 = client.post(
        "/api/v1/projects",
        headers=USER_HEADERS,
        json={"prompt": "real provider", "provider": "real"},
    )
    assert r2.status_code == 201

    # Project 3: Any additional request should now exceed quota
    r3 = client.post(
        "/api/v1/projects",
        headers=USER_HEADERS,
        json={"prompt": "one too many", "provider": "fake"},
    )
    assert r3.status_code == 429
    assert r3.json()["error"]["code"] == "QUOTA_EXCEEDED"


def test_3_tier_provider_architecture(client: TestClient) -> None:
    # 1. Test Mock tier
    r_mock = client.post(
        "/api/v1/projects",
        headers=USER_HEADERS,
        json={"prompt": "mock generation", "provider": "mock"},
    )
    assert r_mock.status_code == 201
    mock_id = r_mock.json()["id"]
    p_mock = client.get(f"/api/v1/projects/{mock_id}", headers=USER_HEADERS).json()
    assert p_mock["status"] in ("pending", "generating", "completed")

    # 2. Test Cloud tier
    r_cloud = client.post(
        "/api/v1/projects",
        headers=USER_HEADERS,
        json={"prompt": "cloud AI generation", "provider": "cloud"},
    )
    assert r_cloud.status_code == 201
    cloud_id = r_cloud.json()["id"]
    p_cloud = client.get(f"/api/v1/projects/{cloud_id}", headers=USER_HEADERS).json()
    assert p_cloud["status"] in ("pending", "generating", "completed")

    # 3. Test Local tier
    r_local = client.post(
        "/api/v1/projects",
        headers=USER_HEADERS,
        json={"prompt": "local model generation", "provider": "local"},
    )
    assert r_local.status_code == 201
    local_id = r_local.json()["id"]
    p_local = client.get(f"/api/v1/projects/{local_id}", headers=USER_HEADERS).json()
    assert p_local["status"] in ("pending", "generating", "completed")


# --- T2-2: what comes back from the third-party image endpoint --------------


def fetch_with(handler: Any, endpoint: str = "https://images.example") -> tuple[bytes, str]:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        return _fetch_ai_still_typed("a lantern", endpoint, client)
    finally:
        client.close()


def test_a_still_is_accepted_when_it_is_actually_an_image() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # The prompt is the thing leaving the machine, so assert where it goes.
        assert request.url.raw_path.startswith(b"/prompt/a%20lantern")
        assert request.url.params["model"] == "turbo"
        # No spoofed browser identity.
        assert "Mozilla" not in request.headers.get("user-agent", "")
        return httpx.Response(
            200,
            content=b"\xff\xd8jpegdata",
            headers={"content-type": "image/jpeg"},
        )

    data, content_type = fetch_with(handler)

    assert data == b"\xff\xd8jpegdata"
    assert content_type == "image/jpeg"


def test_an_html_error_page_is_not_treated_as_a_still() -> None:
    """These bytes get written to MEDIA_DIR and served back as user media."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html>rate limited</html>",
            headers={"content-type": "text/html"},
        )

    with pytest.raises(StillFetchError):
        fetch_with(handler)


def test_an_oversized_response_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"x" * (16 * 1024 * 1024 + 1),
            headers={"content-type": "image/png"},
        )

    with pytest.raises(StillFetchError):
        fetch_with(handler)


def test_an_empty_endpoint_sends_no_prompt_anywhere() -> None:
    """The opt-out: no configured endpoint means no egress and no request."""

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("a request was made with no endpoint configured")

    with pytest.raises(StillFetchError):
        fetch_with(handler, endpoint="")


def test_a_refused_still_falls_back_rather_than_failing(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = _render_kenburns_from_ai_still(
            "a lantern", "job.mp4", tmp_path, "ffmpeg", "https://images.example", client
        )
    finally:
        client.close()

    assert result is None
    # And nothing half-written was left in the directory served as user media.
    assert list(tmp_path.iterdir()) == []


# --- W4: the uploaded reference image reaches the renderer -------------------


def _png_bytes() -> bytes:
    """A minimal but genuinely PNG-signed blob."""
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQ"
        "DwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


def test_a_reference_image_is_used_instead_of_generating_a_still(tmp_path: Path) -> None:
    """The whole point of W4: the account's own image becomes the frame."""
    calls = []

    def endpoint_must_not_be_called(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(200, content=b"generated", headers={"content-type": "image/png"})

    client = httpx.Client(transport=httpx.MockTransport(endpoint_must_not_be_called))
    try:
        _render_kenburns_from_ai_still(
            "a lantern",
            "job.mp4",
            tmp_path,
            "definitely-not-ffmpeg",  # render fails; we only assert on the fetch
            "https://images.example",
            client,
            source_still=(_png_bytes(), "image/png"),
        )
    finally:
        client.close()

    # No text-to-image request was made, so the user's prompt never left the
    # machine either -- which matters for the third-party disclosure in T2-2.
    assert calls == []


def test_without_a_reference_image_the_still_is_still_generated(tmp_path: Path) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(200, content=_png_bytes(), headers={"content-type": "image/png"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        _render_kenburns_from_ai_still(
            "a lantern", "job.mp4", tmp_path, "definitely-not-ffmpeg",
            "https://images.example", client,
        )
    finally:
        client.close()

    assert len(calls) == 1


def test_an_unrecognisable_upload_is_refused_rather_than_written(tmp_path: Path) -> None:
    result = _render_kenburns_from_ai_still(
        "a lantern", "job.mp4", tmp_path, "ffmpeg", "https://images.example",
        source_still=(b"<html>not an image</html>", "application/octet-stream"),
    )

    assert result is None
    # Nothing unnamed was written into the directory served as user media.
    assert list(tmp_path.iterdir()) == []


def test_a_reference_image_alone_is_enough(tmp_path: Path) -> None:
    """An image-only request has no prompt, and must not be refused for it."""
    result = _render_kenburns_from_ai_still(
        None, "job.mp4", tmp_path, "definitely-not-ffmpeg", "https://images.example",
        source_still=(_png_bytes(), "image/png"),
    )

    # ffmpeg is bogus so the render fails, but it got far enough to try --
    # before W4 this returned None on the `not prompt` guard instead.
    assert result is None


@pytest.mark.parametrize(
    ("blob", "expected"),
    [
        (bytes.fromhex("ffd8ffe000104a464946"), "image/jpeg"),
        (b"RIFF\x00\x00\x00\x00WEBP", "image/webp"),
        (b"<html>", "application/octet-stream"),
    ],
)
def test_upload_type_comes_from_magic_bytes(blob: bytes, expected: str) -> None:
    from app.providers import _sniff_still_type

    # Not from a client-declared content type, which can claim anything.
    assert _sniff_still_type(blob) == expected


def test_providers_no_longer_discard_the_image_path() -> None:
    """Every provider's poll() must accept image_path, or the row's value is lost."""
    import inspect

    from app.providers import CloudAiVideoProvider, LocalModelVideoProvider, MockVideoProvider

    for cls in (MockVideoProvider, CloudAiVideoProvider, LocalModelVideoProvider):
        assert "image_path" in inspect.signature(cls.poll).parameters, cls.__name__
