from __future__ import annotations

import json
import logging
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.logging_setup import REDACTED, JsonFormatter, configure_logging, redact

SECRET = "eyJhbGciOiJIUzI1NiJ9.super-secret-token-value"


# --- redaction --------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "authorization",
        "Authorization",
        "token",
        "accessToken",
        "access_token",
        "apiKey",
        "api_key",
        "API-KEY",
        "password",
        "serviceRoleKey",
        "service_role_key",
        "jwtSecret",
        "databaseUrl",
        "signedUrl",
    ],
)
def test_sensitive_keys_are_censored_whatever_their_spelling(key: str) -> None:
    assert redact({key: SECRET}) == {key: REDACTED}


def test_redaction_reaches_nested_structures() -> None:
    payload = {
        "outer": {"headers": {"authorization": SECRET}},
        "list": [{"token": SECRET}, {"safe": "keep"}],
    }

    result = redact(payload)

    assert result["outer"]["headers"]["authorization"] == REDACTED
    assert result["list"][0]["token"] == REDACTED
    assert result["list"][1]["safe"] == "keep"


def test_ordinary_fields_survive() -> None:
    assert redact({"method": "GET", "status": 200, "path": "/x"}) == {
        "method": "GET",
        "status": 200,
        "path": "/x",
    }


def test_strings_are_values_not_containers() -> None:
    # A naive Sequence walk would explode a string into a list of characters.
    assert redact("plain") == "plain"
    assert redact({"message": "hello"}) == {"message": "hello"}


# --- formatter --------------------------------------------------------------


def build_record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord("cretona", logging.INFO, __file__, 1, "request", None, None)
    record.__dict__.update(extra)
    return record


def test_formatter_emits_parseable_json_with_extras() -> None:
    output = JsonFormatter().format(build_record(requestId="r-1", status=200))
    payload = json.loads(output)

    assert payload["message"] == "request"
    assert payload["level"] == "info"
    assert payload["requestId"] == "r-1"
    assert payload["status"] == 200
    assert payload["time"].endswith("Z")


def test_formatter_censors_a_secret_that_reaches_it() -> None:
    output = JsonFormatter().format(build_record(authorization=SECRET))

    assert SECRET not in output
    assert REDACTED in output


def test_formatter_serializes_unexpected_types() -> None:
    payload = json.loads(JsonFormatter().format(build_record(when=object())))

    assert isinstance(payload["when"], str)


# --- wiring -----------------------------------------------------------------


def test_configure_logging_is_idempotent() -> None:
    first = configure_logging("info")
    second = configure_logging("debug")

    assert first is second
    assert len(second.handlers) == 1
    # Ours is the only redacting handler, so records must not also reach root.
    assert second.propagate is False


def test_request_logging_never_records_the_bearer_token(
    supabase_client: TestClient,
    bearer: Callable[..., dict[str, str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    headers = bearer()

    supabase_client.get("/api/v1/projects", headers=headers)
    captured = capsys.readouterr().out

    token = headers["Authorization"].removeprefix("Bearer ")
    assert token not in captured
    assert "Bearer" not in captured


def test_request_log_carries_the_correlation_id(
    client: TestClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "trace-me"})
    captured = capsys.readouterr().out

    assert response.headers["X-Request-ID"] == "trace-me"
    logged = [json.loads(line) for line in captured.splitlines() if line.startswith("{")]
    request_lines = [entry for entry in logged if entry.get("message") == "request"]
    assert request_lines
    assert request_lines[-1]["requestId"] == "trace-me"
    assert request_lines[-1]["status"] == 200
    assert request_lines[-1]["method"] == "GET"
