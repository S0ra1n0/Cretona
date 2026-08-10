from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "demo-output.mp4").write_bytes(b"test-mp4-bytes")
    settings = Settings(
        environment="test",
        auth_mode="dev",
        database_path=tmp_path / "cretona.db",
        media_dir=media_dir,
        prompt_llm_provider="deterministic",
        fake_polls_before_complete=1,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def user_headers() -> dict[str, str]:
    return {"X-Debug-User-Id": "10000000-0000-4000-8000-000000000001"}


@pytest.fixture
def other_user_headers() -> dict[str, str]:
    return {"X-Debug-User-Id": "20000000-0000-4000-8000-000000000002"}

