from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import Settings
from app.generation_log_retention import GenerationLogRetentionWorker
from app.generation_log_service import GenerationLogService
from app.main import create_app
from tests.conftest import USER_A

HEADERS = {"X-Debug-User-Id": USER_A}


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _project(client: TestClient) -> str:
    response = client.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "retention fixture"}
    )
    assert response.status_code == 201
    return response.json()["id"]


def _record_at(
    client: TestClient,
    project_id: str,
    created_at: datetime,
    *,
    provider: str = "fake",
    event: str = "poll",
    http_status: int | None = 200,
    marker: str = "fixture",
) -> None:
    client.app.state.database.record_generation_log(
        {
            "project_id": project_id,
            "provider": provider,
            "request_id": None,
            "event": event,
            "request": {"marker": marker, "apiKey": "must-not-reach-summary"},
            "response": {"payload": "must-not-reach-summary"},
            "http_status": http_status,
            "created_at": _iso(created_at),
        }
    )


def test_retention_deletes_only_rows_strictly_older_than_the_cutoff(
    client: TestClient,
) -> None:
    now = datetime(2026, 8, 12, 12, tzinfo=UTC)
    cutoff = now - timedelta(days=180)
    project_id = _project(client)
    _record_at(
        client,
        project_id,
        cutoff - timedelta(seconds=1),
        provider="old-provider",
        event="error",
        http_status=503,
        marker="expired",
    )
    _record_at(client, project_id, cutoff, marker="boundary")
    _record_at(client, project_id, cutoff + timedelta(seconds=1), marker="recent")

    summary = client.app.state.generation_log.prune(retention_days=180, batch_size=10, now=now)

    remaining_markers = {
        row["request"]["marker"]
        for row in client.app.state.database.generation_logs(project_id)
        if row["request"] and "marker" in row["request"]
    }
    assert remaining_markers == {"boundary", "recent"}
    assert summary.deleted == 1
    assert summary.by_provider == {"old-provider": 1}
    assert summary.by_event == {"error": 1}
    assert summary.by_http_status == {"503": 1}
    assert summary.failed is False


def test_retention_deletes_the_oldest_bounded_batch(client: TestClient) -> None:
    now = datetime(2026, 8, 12, 12, tzinfo=UTC)
    project_id = _project(client)
    for age, marker in ((400, "oldest"), (300, "middle"), (200, "newest-old")):
        _record_at(client, project_id, now - timedelta(days=age), marker=marker)

    first = client.app.state.generation_log.prune(retention_days=180, batch_size=2, now=now)

    remaining_markers = {
        row["request"]["marker"]
        for row in client.app.state.database.generation_logs(project_id)
        if row["request"] and "marker" in row["request"]
    }
    assert first.deleted == 2
    assert first.batch_full is True
    assert remaining_markers == {"newest-old"}

    second = client.app.state.generation_log.prune(retention_days=180, batch_size=2, now=now)
    assert second.deleted == 1
    assert second.batch_full is False


def test_retention_summary_never_contains_provider_payloads(
    client: TestClient, monkeypatch
) -> None:
    now = datetime(2026, 8, 12, 12, tzinfo=UTC)
    project_id = _project(client)
    _record_at(client, project_id, now - timedelta(days=181))
    logged: list[dict] = []

    def capture(_message: str, *, extra: dict) -> None:
        logged.append(extra)

    monkeypatch.setattr("app.generation_log_service.logger.info", capture)

    summary = client.app.state.generation_log.prune(retention_days=180, batch_size=10, now=now)

    rendered = repr(summary)
    assert "must-not-reach-summary" not in rendered
    assert "apiKey" not in rendered
    assert "must-not-reach-summary" not in repr(logged)
    assert "apiKey" not in repr(logged)
    assert logged[0]["byProvider"] == {"fake": 1}


def test_retention_failure_is_best_effort() -> None:
    class BrokenDatabase:
        def prune_generation_logs(self, before: str, limit: int) -> list[dict]:
            raise RuntimeError("database unavailable")

    summary = GenerationLogService(BrokenDatabase()).prune(
        retention_days=180,
        batch_size=10,
        now=datetime(2026, 8, 12, tzinfo=UTC),
    )

    assert summary.deleted == 0
    assert summary.failed is True


def test_retention_worker_starts_runs_and_stops_cleanly() -> None:
    calls = {"count": 0}

    class Service:
        def prune(self, **_kwargs):
            calls["count"] += 1

    settings = SimpleNamespace(
        generation_log_retention_enabled=True,
        generation_log_retention_days=180,
        generation_log_retention_interval_seconds=0.01,
        generation_log_retention_batch_size=10,
    )
    worker = GenerationLogRetentionWorker(Service(), settings)

    async def scenario() -> None:
        worker.start()
        await asyncio.sleep(0.03)
        assert worker.is_running
        await worker.stop()

    asyncio.run(scenario())

    assert calls["count"] >= 1
    assert worker.is_running is False


def test_disabled_retention_worker_does_not_start() -> None:
    settings = SimpleNamespace(generation_log_retention_enabled=False)
    worker = GenerationLogRetentionWorker(object(), settings)

    async def scenario() -> None:
        worker.start()
        assert worker.is_running is False
        await worker.stop()

    asyncio.run(scenario())


def test_app_lifespan_owns_the_retention_worker(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        database_path=tmp_path / "retention-lifecycle.db",
        media_dir=tmp_path / "media",
        poller_enabled=False,
        generation_log_retention_enabled=True,
    )
    app = create_app(settings)

    with TestClient(app):
        assert app.state.generation_log_retention.is_running is True

    assert app.state.generation_log_retention.is_running is False
