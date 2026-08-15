from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import USER_A

USER_HEADERS = {"X-Debug-User-Id": USER_A}


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
    webhook_res = client.post(
        "/api/v1/webhooks/fake",
        json={
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
    webhook_res = client.post(
        "/api/v1/webhooks/fake",
        json={
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
