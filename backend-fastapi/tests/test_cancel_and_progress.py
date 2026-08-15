from fastapi.testclient import TestClient


def test_project_includes_progress_and_step_message(
    client: TestClient, user_headers: dict[str, str]
):
    create_res = client.post(
        "/api/v1/projects",
        headers=user_headers,
        json={"prompt": "slow: glowing lantern floating in wind", "provider": "fake"},
    )
    assert create_res.status_code == 201
    created = create_res.json()
    assert "progressPercent" in created
    assert "stepMessage" in created
    assert created["progressPercent"] == 0

    # Poll step 1
    poll_1 = client.get(f"/api/v1/projects/{created['id']}", headers=user_headers).json()
    assert poll_1["status"] == "generating"
    assert poll_1["progressPercent"] > 0
    assert poll_1["stepMessage"] is not None


def test_cancel_active_project(client: TestClient, user_headers: dict[str, str]):
    # 1. Create a slow project
    create_res = client.post(
        "/api/v1/projects",
        headers=user_headers,
        json={"prompt": "slow: magnificent castle in mountains", "provider": "fake"},
    )
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # 2. Cancel while in-flight
    cancel_res = client.post(
        f"/api/v1/projects/{project_id}/cancel",
        headers=user_headers,
    )
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data["cancelled"] is True
    assert cancel_data["projectId"] == project_id
    assert cancel_data["quotaRefunded"] is True

    # 3. Read back project to verify state is failed with error_code = cancelled
    proj_res = client.get(f"/api/v1/projects/{project_id}", headers=user_headers)
    assert proj_res.status_code == 200
    proj = proj_res.json()
    assert proj["status"] == "failed"
    assert proj["errorMessage"] == "Generation was cancelled by the user."

    # 4. Attempt to cancel again should fail with 409 CONFLICT
    second_cancel = client.post(
        f"/api/v1/projects/{project_id}/cancel",
        headers=user_headers,
    )
    assert second_cancel.status_code == 409
    assert second_cancel.json()["error"]["code"] == "CONFLICT"


def test_cancel_rejects_unowned_project(client: TestClient, user_headers: dict[str, str]):
    res = client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/cancel",
        headers=user_headers,
    )
    assert res.status_code == 404
