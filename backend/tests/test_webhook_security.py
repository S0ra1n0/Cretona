"""Webhook signature verification (R-1).

`POST /api/v1/webhooks/{provider}` is the only unauthenticated route in the
API. The signature is the whole of its access control, so these tests assert
the refusals rather than the happy path, which lives in
test_webhooks_and_providers.py.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.webhook_verification import signing_payload
from tests.conftest import USER_A, WEBHOOK_SECRET
from tests.test_webhooks_and_providers import post_webhook, sign

USER_HEADERS = {"X-Debug-User-Id": USER_A}


def make_project(client: TestClient) -> str:
    return client.post(
        "/api/v1/projects",
        headers=USER_HEADERS,
        json={"prompt": "victim project", "provider": "fake"},
    ).json()["id"]


def assert_refused(response: Any) -> None:
    assert response.status_code == 401, response.text
    body = response.json()
    assert body["error"]["code"] == "UNAUTHENTICATED"
    # One message for every rejection, so it is not an oracle for probing.
    assert body["error"]["message"] == "Webhook signature could not be verified."


# --- refusals ---------------------------------------------------------------


def test_an_unsigned_webhook_is_refused(client: TestClient) -> None:
    """The vulnerability this fixes.

    Before R-1 this call completed a stranger's project.
    """
    project_id = make_project(client)

    response = client.post(
        "/api/v1/webhooks/fake",
        json={"project_id": project_id, "status": "succeeded"},
    )

    assert_refused(response)
    assert (
        client.get(f"/api/v1/projects/{project_id}", headers=USER_HEADERS).json()["status"]
        != "completed"
    )


def test_a_wrongly_signed_webhook_is_refused(client: TestClient) -> None:
    project_id = make_project(client)

    response = post_webhook(
        client,
        {"project_id": project_id, "status": "succeeded"},
        secret="an-attacker-guessed-secret",
    )

    assert_refused(response)


def test_a_tampered_body_is_refused(client: TestClient) -> None:
    """A captured signature does not travel to a different payload."""
    project_id = make_project(client)
    _, headers = sign({"project_id": project_id, "status": "failed"})

    forged = json.dumps({"project_id": project_id, "status": "succeeded"}).encode()
    response = client.post("/api/v1/webhooks/fake", content=forged, headers=headers)

    assert_refused(response)


@pytest.mark.parametrize("value", ["", "sha256=", "not-hex", "sha256=deadbeef"])
def test_malformed_signature_headers_are_refused(client: TestClient, value: str) -> None:
    body = json.dumps({"status": "succeeded"}).encode()

    response = client.post(
        "/api/v1/webhooks/fake",
        content=body,
        headers={"X-Cretona-Signature": value, "Content-Type": "application/json"},
    )

    assert_refused(response)


@pytest.mark.parametrize("provider", ["fake", "real", "wan21"])
def test_every_provider_verifies(client: TestClient, provider: str) -> None:
    # A single unverified adapter would reopen the hole for all of them.
    response = client.post(
        f"/api/v1/webhooks/{provider}",
        json={"status": "succeeded"},
    )

    assert_refused(response)


def test_ssrf_payload_never_reaches_storage(client: TestClient, monkeypatch) -> None:
    """The consequence, not just the status code.

    An accepted webhook passes `video_url` to store_video, which fetches it.
    An unsigned request must not get that far.
    """
    project_id = make_project(client)
    fetched: list[str] = []
    monkeypatch.setattr(
        client.app.state.storage,
        "store_video",
        lambda owner, pid, source: fetched.append(source) or "x",
    )

    client.post(
        "/api/v1/webhooks/fake",
        json={
            "project_id": project_id,
            "status": "succeeded",
            "video_url": "http://169.254.169.254/latest/meta-data/",
        },
    )

    assert fetched == []


# --- fail closed ------------------------------------------------------------


@pytest.fixture
def unconfigured(tmp_path: Path) -> Iterator[TestClient]:
    media = tmp_path / "media"
    media.mkdir()
    (media / "demo-output.mp4").write_bytes(b"test-mp4-bytes")
    settings = Settings(
        environment="test",
        auth_mode="dev",
        database_path=tmp_path / "nosecret.db",
        media_dir=media,
        prompt_llm_provider="deterministic",
        poller_enabled=False,
        generation_log_retention_enabled=False,
        webhook_secret="",
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client


def test_no_configured_secret_accepts_nothing(unconfigured: TestClient) -> None:
    """Fails closed: an unverifiable webhook is worth less than no webhook."""
    body = json.dumps({"status": "succeeded"}).encode()
    digest = hmac.new(b"", body, hashlib.sha256).hexdigest()

    response = unconfigured.post(
        "/api/v1/webhooks/fake",
        content=body,
        headers={"X-Cretona-Signature": digest, "Content-Type": "application/json"},
    )

    assert_refused(response)


# --- accepted --------------------------------------------------------------


def test_a_correctly_signed_webhook_is_accepted(client: TestClient) -> None:
    project_id = make_project(client)

    response = post_webhook(client, {"project_id": project_id, "status": "failed"})

    assert response.status_code == 200
    assert response.json()["projectId"] == project_id


def test_a_bare_hex_signature_is_accepted(client: TestClient) -> None:
    # Providers differ on whether they prefix the digest.
    project_id = make_project(client)
    sent_at = str(int(datetime.now(UTC).timestamp()))
    body = json.dumps({"project_id": project_id, "status": "failed"}).encode()
    digest = hmac.new(
        WEBHOOK_SECRET.encode(), signing_payload(sent_at, body), hashlib.sha256
    ).hexdigest()

    response = client.post(
        "/api/v1/webhooks/fake",
        content=body,
        headers={
            "X-Cretona-Signature": digest,
            "X-Cretona-Timestamp": sent_at,
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200


# --- T2-4: freshness --------------------------------------------------------


def test_a_replayed_delivery_is_refused_once_it_is_stale(client: TestClient) -> None:
    """The vulnerability this fixes.

    HMAC proves who sent the bytes, never when. A capture of one valid
    delivery used to stay valid forever, so anyone who saw a webhook once
    could resend it and drive the project again.
    """
    project_id = make_project(client)
    captured_at = str(int(datetime.now(UTC).timestamp()) - 3600)
    body, headers = sign({"project_id": project_id, "status": "succeeded"}, timestamp=captured_at)

    response = client.post("/api/v1/webhooks/fake", content=body, headers=headers)

    assert_refused(response)
    assert (
        client.get(f"/api/v1/projects/{project_id}", headers=USER_HEADERS).json()["status"]
        != "completed"
    )


def test_a_future_dated_delivery_is_refused(client: TestClient) -> None:
    """A sender with a fast clock would otherwise mint long-lived requests."""
    project_id = make_project(client)
    ahead = str(int(datetime.now(UTC).timestamp()) + 3600)
    body, headers = sign({"project_id": project_id, "status": "succeeded"}, timestamp=ahead)

    assert_refused(client.post("/api/v1/webhooks/fake", content=body, headers=headers))


def test_a_delivery_with_no_timestamp_is_refused(client: TestClient) -> None:
    """The pre-T2-4 signing scheme is no longer accepted."""
    project_id = make_project(client)
    body = json.dumps({"project_id": project_id, "status": "succeeded"}).encode()
    digest = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    response = client.post(
        "/api/v1/webhooks/fake",
        content=body,
        headers={"X-Cretona-Signature": digest, "Content-Type": "application/json"},
    )

    assert_refused(response)


def test_the_timestamp_cannot_be_refreshed_without_the_secret(client: TestClient) -> None:
    """The timestamp is inside the MAC, so editing it breaks the signature."""
    project_id = make_project(client)
    captured_at = str(int(datetime.now(UTC).timestamp()) - 3600)
    body, headers = sign({"project_id": project_id, "status": "succeeded"}, timestamp=captured_at)

    headers["X-Cretona-Timestamp"] = str(int(datetime.now(UTC).timestamp()))
    assert_refused(client.post("/api/v1/webhooks/fake", content=body, headers=headers))


@pytest.mark.parametrize("value", ["", "   ", "not-a-number", "1.5e9"])
def test_malformed_timestamps_are_refused(client: TestClient, value: str) -> None:
    project_id = make_project(client)
    body, headers = sign({"project_id": project_id, "status": "succeeded"})
    headers["X-Cretona-Timestamp"] = value

    assert_refused(client.post("/api/v1/webhooks/fake", content=body, headers=headers))
