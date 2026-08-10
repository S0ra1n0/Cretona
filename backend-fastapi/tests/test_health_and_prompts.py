from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_is_public_and_has_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
    assert response.headers["X-Request-ID"]


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "demo-request"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "demo-request"


def test_prompt_enhancement_reports_deterministic_fallback(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/prompts/enhance",
        headers=user_headers,
        json={"prompt": "a cat astronaut", "aspectRatio": "16:9"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["originalPrompt"] == "a cat astronaut"
    assert "camera movement" in body["enhancedPrompt"]
    assert body["provider"] == "deterministic"
    assert body["usedFallback"] is True


def test_prompt_validation_uses_contract_error_envelope(
    client: TestClient,
    user_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/prompts/enhance",
        headers=user_headers,
        json={"prompt": ""},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["requestId"]
    assert body["error"]["details"]


def test_invalid_debug_user_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/v1/projects",
        headers={"X-Debug-User-Id": "not-a-uuid"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

