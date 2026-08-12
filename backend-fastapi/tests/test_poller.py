from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.poller import JobPoller
from tests.conftest import USER_A

HEADERS = {"X-Debug-User-Id": USER_A}


@pytest.fixture
def polled(tmp_path: Path) -> Iterator[TestClient]:
    media = tmp_path / "media"
    media.mkdir()
    (media / "demo-output.mp4").write_bytes(b"test-mp4-bytes")
    settings = Settings(
        environment="test",
        auth_mode="dev",
        database_path=tmp_path / "poll.db",
        media_dir=media,
        prompt_llm_provider="deterministic",
        fake_polls_before_complete=1,
        poller_enabled=False,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client


def poller(client: TestClient) -> JobPoller:
    return client.app.state.poller


def test_a_project_completes_without_anyone_reading_it(polled: TestClient) -> None:
    created = polled.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "unattended"}
    ).json()
    assert created["status"] == "pending"

    # pending -> generating, then generating -> completed. No client read.
    poller(polled).run_once()
    poller(polled).run_once()

    row = polled.app.state.database.get_project(created["id"], USER_A)
    assert row["status"] == "completed"
    assert row["video_path"]


def test_the_batch_reports_what_it_touched(polled: TestClient) -> None:
    for index in range(3):
        polled.post("/api/v1/projects", headers=HEADERS, json={"prompt": f"p{index}"})

    assert poller(polled).run_once() == 3


def test_terminal_projects_are_left_alone(polled: TestClient) -> None:
    polled.post("/api/v1/projects", headers=HEADERS, json={"prompt": "done soon"})
    poller(polled).run_once()
    poller(polled).run_once()

    # Completed, so there is nothing in flight left to claim.
    assert poller(polled).run_once() == 0


def test_deleted_projects_are_not_claimed(polled: TestClient) -> None:
    created = polled.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "abandoned"}
    ).json()
    polled.delete(f"/api/v1/projects/{created['id']}", headers=HEADERS)

    assert poller(polled).run_once() == 0


def test_the_batch_size_is_respected(polled: TestClient) -> None:
    for index in range(4):
        polled.post("/api/v1/projects", headers=HEADERS, json={"prompt": f"p{index}"})

    polled.app.state.settings.poll_batch_size = 2

    assert poller(polled).run_once() == 2


def test_one_bad_project_does_not_stall_the_batch(polled: TestClient) -> None:
    for index in range(3):
        polled.post("/api/v1/projects", headers=HEADERS, json={"prompt": f"p{index}"})

    calls = {"n": 0}
    real_advance = polled.app.state.project_service.advance

    def flaky(row: dict) -> dict:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("poisoned row")
        return real_advance(row)

    polled.app.state.project_service.advance = flaky

    # Two of three advanced; the failure did not abort the rest.
    assert poller(polled).run_once() == 2
    assert calls["n"] == 3


def test_read_and_poller_share_one_state_machine(polled: TestClient) -> None:
    created = polled.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "shared"}
    ).json()

    # Poller does the first step, a read does the second.
    poller(polled).run_once()
    body = polled.get(f"/api/v1/projects/{created['id']}", headers=HEADERS).json()

    assert body["status"] == "completed"


def test_the_loop_starts_and_stops_cleanly(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    settings = Settings(
        environment="test",
        database_path=tmp_path / "loop.db",
        media_dir=media,
        poller_enabled=True,
        poll_interval_seconds=0.01,
    )
    app = create_app(settings)
    app.state.database.initialize()
    job_poller = app.state.poller

    async def scenario() -> None:
        job_poller.start()
        # Long enough for several iterations at a 10ms interval.
        await asyncio.sleep(0.05)
        assert job_poller.is_running
        await job_poller.stop()

    asyncio.run(scenario())

    assert job_poller.is_running is False


def test_a_disabled_poller_does_not_start(polled: TestClient) -> None:
    poller(polled).start()

    assert poller(polled).is_running is False


# --- leases (B-2) -----------------------------------------------------------


def second_poller(client: TestClient) -> JobPoller:
    """A distinct instance sharing the same database."""
    return JobPoller(
        client.app.state.database,
        client.app.state.project_service,
        client.app.state.settings,
    )


def lease_of(client: TestClient, project_id: str) -> tuple[str | None, str | None]:
    row = client.app.state.database.get_project(project_id, USER_A)
    return row["lease_owner"], row["lease_expires_at"]


def test_two_pollers_do_not_claim_the_same_work(polled: TestClient) -> None:
    """The bug B-2 exists to fix.

    The old claim held a row lock only for its own transaction, which committed
    before any advancing happened. Both pollers saw the same rows and would
    submit the same project to the provider twice.
    """
    for index in range(3):
        polled.post("/api/v1/projects", headers=HEADERS, json={"prompt": f"p{index}"})

    first = polled.app.state.database.claim_in_flight_projects(
        10, owner="poller-a", now="2026-01-01T00:00:00Z", lease_until="2999-01-01T00:00:00Z"
    )
    second = polled.app.state.database.claim_in_flight_projects(
        10, owner="poller-b", now="2026-01-01T00:00:00Z", lease_until="2999-01-01T00:00:00Z"
    )

    assert len(first) == 3
    assert second == []


def test_an_expired_lease_is_reclaimable(polled: TestClient) -> None:
    """Recovery path: a crashed poller must not strand work forever."""
    created = polled.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "abandoned"}
    ).json()

    polled.app.state.database.claim_in_flight_projects(
        10, owner="dead-poller", now="2026-01-01T00:00:00Z", lease_until="2026-01-01T00:01:00Z"
    )

    # Now, which is after that lease lapsed.
    reclaimed = polled.app.state.database.claim_in_flight_projects(
        10, owner="live-poller", now="2026-06-01T00:00:00Z", lease_until="2999-01-01T00:00:00Z"
    )

    assert [row["id"] for row in reclaimed] == [created["id"]]


def test_a_batch_releases_its_rows(polled: TestClient) -> None:
    created = polled.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "released"}
    ).json()

    poller(polled).run_once()

    # Released, so the very next pass can pick it up rather than waiting out
    # the lease.
    assert lease_of(polled, created["id"]) == (None, None)
    assert poller(polled).run_once() == 1


def test_a_failed_advance_still_releases(polled: TestClient, monkeypatch) -> None:
    created = polled.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "poisoned"}
    ).json()

    def explode(row: dict) -> dict:
        raise RuntimeError("poisoned row")

    monkeypatch.setattr(polled.app.state.project_service, "advance", explode)
    poller(polled).run_once()

    # A transient error must not hold the row for the whole lease.
    assert lease_of(polled, created["id"]) == (None, None)


def test_release_is_scoped_to_the_holder(polled: TestClient) -> None:
    created = polled.post(
        "/api/v1/projects", headers=HEADERS, json={"prompt": "contested"}
    ).json()
    database = polled.app.state.database
    database.claim_in_flight_projects(
        10, owner="holder", now="2026-01-01T00:00:00Z", lease_until="2999-01-01T00:00:00Z"
    )

    database.release_lease(created["id"], "someone-else")

    # A lapsed poller must not clear the new holder's claim.
    assert lease_of(polled, created["id"])[0] == "holder"


def test_each_poller_instance_has_its_own_identity(polled: TestClient) -> None:
    assert poller(polled).instance_id != second_poller(polled).instance_id
    assert poller(polled).instance_id.startswith("poller-")
