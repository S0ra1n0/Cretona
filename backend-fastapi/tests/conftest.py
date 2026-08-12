from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.db_safety import assert_disposable_database

USER_A = "10000000-0000-4000-8000-000000000001"
USER_B = "20000000-0000-4000-8000-000000000002"

# Test-only signing material. This is not a Supabase value and never was; the
# real secret is supplied per machine through CRETONA_SUPABASE_JWT_SECRET.
JWT_SECRET = "local-test-signing-key-not-a-supabase-secret"
JWT_AUDIENCE = "authenticated"
JWT_ISSUER = "https://project-ref.supabase.co/auth/v1"

TokenFactory = Callable[..., str]


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    media_dir = tmp_path / "media"
    media_dir.mkdir(exist_ok=True)
    (media_dir / "demo-output.mp4").write_bytes(b"test-mp4-bytes")
    defaults: dict[str, Any] = {
        "environment": "test",
        "auth_mode": "dev",
        "database_path": tmp_path / "cretona.db",
        "media_dir": media_dir,
        "prompt_llm_provider": "deterministic",
        "fake_polls_before_complete": 1,
        # Off by default so tests observe the read-driven state machine without
        # a background task racing them. test_poller.py enables it explicitly.
        "poller_enabled": False,
        # Retention has its own lifecycle. Tests call it explicitly so an
        # immediate startup sweep cannot make time-sensitive assertions race.
        "generation_log_retention_enabled": False,
    }
    return Settings(**{**defaults, **overrides})


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = _settings(tmp_path)
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def supabase_client(tmp_path: Path) -> Iterator[TestClient]:
    """A client running the deployed identity profile, not dev injection."""
    settings = _settings(
        tmp_path,
        auth_mode="supabase",
        supabase_jwt_secret=JWT_SECRET,
        supabase_jwt_audience=JWT_AUDIENCE,
        supabase_jwt_issuer=JWT_ISSUER,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        # A verified token still needs a profile row, exactly as the Supabase
        # signup trigger would have created one.
        database = test_client.app.state.database
        database.upsert_user(USER_A, email="a@example.com")
        database.upsert_user(USER_B, email="b@example.com")
        yield test_client


@pytest.fixture
def postgres_url() -> str:
    """The Postgres test target, or skip.

    Credential-free machines still run the whole SQLite suite; only the
    Postgres parity tests opt out.
    """
    url = os.environ.get("CRETONA_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("Set CRETONA_TEST_DATABASE_URL to run the Postgres parity tests.")
    # Raises rather than skips: pointing this at a real database is a mistake
    # worth stopping on, not one worth quietly stepping around.
    assert_disposable_database(url)
    return url


@pytest.fixture
def postgres_client(tmp_path: Path, postgres_url: str) -> Iterator[TestClient]:
    psycopg = pytest.importorskip("psycopg")

    schema = (Path(__file__).parent / "postgres_schema.sql").read_text(encoding="utf-8")
    # Fail fast. Without a timeout, a configured-but-unreachable database (a
    # stopped container, a sleeping laptop) hangs the whole suite instead of
    # reporting that it cannot connect.
    with psycopg.connect(postgres_url, autocommit=True, connect_timeout=5) as connection:
        connection.execute(schema)
        for user_id, email in ((USER_A, "a@example.com"), (USER_B, "b@example.com")):
            connection.execute(
                "INSERT INTO public.users (id, email) VALUES (%s, %s)",
                (user_id, email),
            )

    settings = _settings(
        tmp_path,
        auth_mode="supabase",
        supabase_jwt_secret=JWT_SECRET,
        supabase_jwt_audience=JWT_AUDIENCE,
        supabase_jwt_issuer=JWT_ISSUER,
        database_backend="postgres",
        database_url=postgres_url,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def user_headers() -> dict[str, str]:
    return {"X-Debug-User-Id": USER_A}


@pytest.fixture
def other_user_headers() -> dict[str, str]:
    return {"X-Debug-User-Id": USER_B}


@pytest.fixture
def make_token() -> TokenFactory:
    """Mint tokens independently of the verifier, so signatures are real."""

    def _make(
        *,
        subject: str = USER_A,
        secret: str = JWT_SECRET,
        audience: str | list[str] | None = JWT_AUDIENCE,
        issuer: str | None = JWT_ISSUER,
        algorithm: str = "HS256",
        expires_in: int = 3600,
        email: str | None = None,
        include_subject: bool = True,
        signature: str | None = None,
    ) -> str:
        issued_at = int(time.time())
        header = {"alg": algorithm, "typ": "JWT"}
        payload: dict[str, Any] = {"iat": issued_at, "exp": issued_at + expires_in}
        if include_subject:
            payload["sub"] = subject
        if audience is not None:
            payload["aud"] = audience
        if issuer is not None:
            payload["iss"] = issuer
        if email is not None:
            payload["email"] = email

        signing_input = f"{_segment(header)}.{_segment(payload)}"
        if signature is not None:
            return f"{signing_input}.{signature}"

        digest = {"HS256": hashlib.sha256, "HS512": hashlib.sha512}[algorithm]
        raw = hmac.new(secret.encode(), signing_input.encode(), digest).digest()
        return f"{signing_input}.{_b64url(raw)}"

    return _make


@pytest.fixture
def bearer(make_token: TokenFactory) -> Callable[..., dict[str, str]]:
    def _bearer(**kwargs: Any) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(**kwargs)}"}

    return _bearer


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _segment(value: dict[str, Any]) -> str:
    return _b64url(json.dumps(value, separators=(",", ":")).encode())
