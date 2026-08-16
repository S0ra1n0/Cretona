from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import USER_A, WEBHOOK_SECRET

USER_HEADERS = {"X-Debug-User-Id": USER_A}


def sign(payload: dict[str, Any], secret: str = WEBHOOK_SECRET) -> tuple[bytes, dict[str, str]]:
    """Sign the exact bytes that will be sent.

    The server verifies the raw body, so the test must post `content=` rather
    than `json=`; re-serializing would change the bytes the signature covers.
    """
    body = json.dumps(payload).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return body, {
        "X-Cretona-Signature": f"sha256={digest}",
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
