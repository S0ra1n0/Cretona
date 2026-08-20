from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import safe_request_id
from app.prompt_service import PromptEnhancer
from app.schemas import PromptEnhanceRequest


def test_health_is_public_and_has_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
    assert response.headers["X-Request-ID"]


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "demo-request"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "demo-request"


def test_unsafe_request_id_is_replaced(client: TestClient) -> None:
    supplied = "x" * 65
    response = client.get("/api/v1/health", headers={"X-Request-ID": supplied})

    observed = response.headers["X-Request-ID"]
    assert response.status_code == 200
    assert observed != supplied
    assert safe_request_id(observed) == observed


class BrokenDatabase:
    @contextmanager
    def connect(self):  # type: ignore[no-untyped-def]
        raise RuntimeError("postgresql://user:private-password@db.example.test/postgres")
        yield  # pragma: no cover - keeps this a context manager


def test_health_failure_does_not_expose_database_details(client: TestClient) -> None:
    original: Any = client.app.state.database
    client.app.state.database = BrokenDatabase()
    try:
        for path in ("/health", "/healthz", "/api/v1/health"):
            response = client.get(path)
            assert response.status_code == 503
            assert response.json()["error"] == {
                "code": "SERVICE_UNAVAILABLE",
                "message": "Database connectivity check failed.",
            }
            assert "private-password" not in response.text
            assert "db.example.test" not in response.text
    finally:
        client.app.state.database = original


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


def test_ollama_request_is_bounded_and_unloads_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "qwen3:4b-instruct-2507-q4_K_M"
        assert payload["stream"] is False
        assert payload["keep_alive"] == 0
        assert payload["options"] == {
            "num_ctx": 4096,
            "num_predict": 180,
            "temperature": 0.2,
        }
        return httpx.Response(200, json={"response": "A bounded cinematic prompt."})

    enhancer = PromptEnhancer(
        Settings(prompt_llm_provider="ollama"),
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(
        enhancer.enhance(PromptEnhanceRequest(prompt="paper dragon", aspectRatio="16:9"))
    )

    assert result.provider == "ollama"
    assert result.used_fallback is False
    assert result.enhanced_prompt == "A bounded cinematic prompt."
