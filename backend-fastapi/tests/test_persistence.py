from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_projects_survive_application_restart(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        database_path=tmp_path / "persistent.db",
        media_dir=tmp_path / "media",
    )

    with TestClient(create_app(settings)) as first_client:
        created = first_client.post(
            "/api/v1/projects",
            json={"prompt": "persistent paper city"},
        )
        assert created.status_code == 201
        project_id = created.json()["id"]

    with TestClient(create_app(settings)) as second_client:
        listed = second_client.get("/api/v1/projects")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [project_id]

