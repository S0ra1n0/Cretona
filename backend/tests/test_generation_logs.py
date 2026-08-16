from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.generation_log_service import GenerationLogService
from app.logging_setup import REDACTED
from tests.conftest import USER_A

HEADERS = {"X-Debug-User-Id": USER_A}


def drive(client: TestClient, prompt: str = "a lantern") -> str:
    created = client.post("/api/v1/projects", headers=HEADERS, json={"prompt": prompt}).json()
    client.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)
    client.get(f"/api/v1/projects/{created['id']}", headers=HEADERS)
    return created["id"]


def events(client: TestClient, project_id: str) -> list[str]:
    return [row["event"] for row in client.app.state.database.generation_logs(project_id)]


def test_a_successful_generation_leaves_a_full_trail(client: TestClient) -> None:
    project_id = drive(client)

    # The first read only moves pending -> generating; the poll happens on the
    # second, and the download follows it.
    assert events(client, project_id) == ["submit", "poll", "download"]


def test_a_failed_generation_records_the_poll_that_failed(client: TestClient) -> None:
    project_id = drive(client, "fail:content_policy unsafe")

    recorded = client.app.state.database.generation_logs(project_id)
    poll = [row for row in recorded if row["event"] == "poll"][-1]

    assert poll["response"]["status"] == "failed"
    assert poll["response"]["failure"] == "content_policy"


def test_the_submit_entry_carries_the_provider_job_id(client: TestClient) -> None:
    project_id = drive(client)

    submit = client.app.state.database.generation_logs(project_id)[0]

    assert submit["event"] == "submit"
    assert submit["provider"] == "fake"
    assert submit["request_id"].startswith("fake_")
    assert submit["request"]["prompt"] == "a lantern"


def test_the_download_entry_records_where_the_video_landed(client: TestClient) -> None:
    project_id = drive(client)

    download = client.app.state.database.generation_logs(project_id)[-1]

    assert download["event"] == "download"
    assert download["response"]["storedPath"].endswith("video.mp4")


def test_logs_are_scoped_to_their_project(client: TestClient) -> None:
    first = drive(client, "first")
    second = drive(client, "second")

    assert len(events(client, first)) == 3
    assert len(events(client, second)) == 3
    assert first != second


# --- redaction --------------------------------------------------------------


class RecordingDatabase:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def record_generation_log(self, values: dict) -> None:
        self.rows.append(values)


def test_secrets_are_redacted_before_they_are_stored() -> None:
    database = RecordingDatabase()

    GenerationLogService(database).record(
        project_id="p1",
        provider="fake",
        event="submit",
        request={"prompt": "hi", "apiKey": "sk-live-123", "nested": {"token": "t-456"}},
        response={"signedUrl": "https://bucket/x?token=abc"},
    )

    stored = database.rows[0]
    assert stored["request"]["apiKey"] == REDACTED
    assert stored["request"]["nested"]["token"] == REDACTED
    assert stored["response"]["signedUrl"] == REDACTED
    # The useful part survives.
    assert stored["request"]["prompt"] == "hi"


def test_a_write_failure_does_not_break_the_generation() -> None:
    class BrokenDatabase:
        def record_generation_log(self, values: dict) -> None:
            raise RuntimeError("table is gone")

    # Must not raise: failing a generation because its audit row could not be
    # written would trade a working feature for a diagnostic.
    GenerationLogService(BrokenDatabase()).record(project_id="p1", provider="fake", event="submit")


@pytest.mark.parametrize("event", ["submit", "poll", "webhook", "download", "error"])
def test_every_contract_event_is_accepted(client: TestClient, event: str) -> None:
    project_id = drive(client)

    GenerationLogService(client.app.state.database).record(
        project_id=project_id,
        provider="fake",
        event=event,  # type: ignore[arg-type]
    )

    assert event in events(client, project_id)
