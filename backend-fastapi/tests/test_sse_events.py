from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import USER_A


def test_sse_project_events_stream(client: TestClient):
    headers = {"X-Debug-User-Id": USER_A}

    # 1. Create a project
    create_res = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "prompt": "A glowing jellyfish floating in deep space",
            "provider": "fake",
            "options": {"durationSeconds": 5, "aspectRatio": "16:9"},
        },
    )
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # 2. Connect to SSE events stream
    with client.stream(
        "GET",
        f"/api/v1/projects/{project_id}/events",
        headers=headers,
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        events_received = []
        for line in response.iter_lines():
            if line.startswith("data:"):
                events_received.append(line)
                if len(events_received) >= 1:
                    break

        assert len(events_received) >= 1
