from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient


def create_project(
    client: TestClient,
    headers: dict[str, str],
    *,
    prompt: str = "A paper boat crossing a neon river",
    idempotency_key: str | None = None,
) -> dict:
    request_headers = dict(headers)
    if idempotency_key:
        request_headers["Idempotency-Key"] = idempotency_key
    response = client.post(
        "/api/v1/projects",
        headers=request_headers,
        json={
            "prompt": prompt,
            "provider": "fake",
            "options": {"durationSeconds": 5, "aspectRatio": "16:9"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_project_lifecycle_reaches_playable_completed_video(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    created = create_project(client, user_headers)
    assert created["status"] == "pending"
    assert created["videoUrl"] is None

    generating = client.get(f"/api/v1/projects/{created['id']}", headers=user_headers)
    assert generating.status_code == 200
    assert generating.json()["status"] == "generating"

    completed = client.get(f"/api/v1/projects/{created['id']}", headers=user_headers)
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "completed"
    assert body["videoUrl"].endswith("/media/demo-output.mp4")
    assert body["completedAt"]

    media = client.get("/media/demo-output.mp4")
    assert media.status_code == 200
    assert media.content == b"test-mp4-bytes"


def test_idempotency_returns_the_original_project(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    key = str(uuid4())
    first = create_project(client, user_headers, idempotency_key=key)
    second = create_project(client, user_headers, idempotency_key=key)

    assert second["id"] == first["id"]
    listed = client.get("/api/v1/projects", headers=user_headers).json()
    assert len(listed["items"]) == 1


def test_owner_cannot_discover_another_users_project(
    client: TestClient,
    user_headers: dict[str, str],
    other_user_headers: dict[str, str],
) -> None:
    created = create_project(client, user_headers)
    response = client.get(
        f"/api/v1/projects/{created['id']}",
        headers=other_user_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_fake_failure_is_mapped_and_can_be_retried(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    created = create_project(client, user_headers, prompt="fail:content_policy unsafe input")
    client.get(f"/api/v1/projects/{created['id']}", headers=user_headers)
    failed = client.get(f"/api/v1/projects/{created['id']}", headers=user_headers)

    assert failed.status_code == 200
    body = failed.json()
    assert body["status"] == "failed"
    assert body["errorMessage"] == (
        "The prompt or image could not be used. Try different content."
    )
    assert "Fake provider" not in body["errorMessage"]

    retried = client.post(
        f"/api/v1/projects/{created['id']}/retry",
        headers=user_headers,
    )
    assert retried.status_code == 202
    assert retried.json()["status"] == "pending"


def test_generating_project_cannot_be_deleted(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    created = create_project(client, user_headers)
    client.get(f"/api/v1/projects/{created['id']}", headers=user_headers)

    response = client.delete(f"/api/v1/projects/{created['id']}", headers=user_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_pending_project_can_be_deleted(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    created = create_project(client, user_headers)
    response = client.delete(f"/api/v1/projects/{created['id']}", headers=user_headers)

    assert response.status_code == 204
    missing = client.get(f"/api/v1/projects/{created['id']}", headers=user_headers)
    assert missing.status_code == 404


def test_create_requires_prompt_or_image(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    response = client.post("/api/v1/projects", headers=user_headers, json={})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_provider_is_rejected(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/projects",
        headers=user_headers,
        json={"prompt": "hello", "provider": "runway"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["issue"] == "unknown_provider"


def test_invalid_idempotency_key_is_rejected(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/projects",
        headers={**user_headers, "Idempotency-Key": "not-a-uuid"},
        json={"prompt": "hello"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_cursor_pagination_has_no_duplicates(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    for index in range(3):
        create_project(client, user_headers, prompt=f"project {index}")

    first = client.get("/api/v1/projects?limit=2", headers=user_headers).json()
    assert len(first["items"]) == 2
    assert first["page"]["hasMore"] is True

    cursor = first["page"]["nextCursor"]
    second = client.get(
        f"/api/v1/projects?limit=2&cursor={cursor}",
        headers=user_headers,
    ).json()
    assert len(second["items"]) == 1
    assert second["page"]["hasMore"] is False
    ids = {item["id"] for item in first["items"] + second["items"]}
    assert len(ids) == 3


def test_invalid_cursor_uses_validation_error(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    response = client.get("/api/v1/projects?cursor=%%%", headers=user_headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

