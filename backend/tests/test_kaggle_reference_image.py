"""The reference image reaches the worker, or the job stays honestly text-only.

Image-to-video is blocked at two layers today, and only one of them is being
removed. `supabase/016` lets the worker *read* the still belonging to the
project it holds, because migration 015's grant matches
`<user_id>/<project_id>/thumbnail.jpg` exactly and a reference image is stored
as `<user_id>/<yyyy-mm-dd>/<uuid>`. The claim filter `image_path is null` stays
until a worker exists that can honour an image, so nothing here makes an
uploaded picture get silently ignored -- the job is never handed over at all.

These tests cover the plumbing that ships ahead of that decision.
"""

from __future__ import annotations

import urllib.error
from pathlib import Path
from uuid import UUID

import pytest

import kaggle_worker
from kaggle_worker import AuthSession, Job, SupabaseWorkerClient, WorkerConfig

WORKER = UUID("30000000-0000-4000-8000-000000000003")
USER = UUID("10000000-0000-4000-8000-000000000001")
PROJECT = UUID("40000000-0000-4000-8000-000000000004")
REFERENCE = f"{USER}/2026-09-05/2f1b6c1e-0000-4000-8000-00000000abcd.jpg"


def _row(**overrides):
    row = {
        "project_id": PROJECT,
        "user_id": USER,
        "prompt": "a paper dragon",
        "duration_seconds": 4,
        "aspect_ratio": "16:9",
    }
    row.update(overrides)
    return row


def _config(tmp_path: Path) -> WorkerConfig:
    return WorkerConfig(
        database_url="postgresql://worker:secret@localhost/cretona",
        supabase_url="https://project.supabase.co",
        publishable_key="publishable-test-key",
        worker_email="worker@example.com",
        worker_password="secret",
        output_dir=tmp_path,
    )


# --- Job.from_row ------------------------------------------------------------


def test_a_job_without_an_image_is_text_only() -> None:
    assert Job.from_row(_row()).image_path is None


def test_a_claim_result_with_no_image_column_is_text_only() -> None:
    """A worker bundle can be newer than the database it claims from.

    Before `supabase/016` the claim function returns five columns. That is an
    older database, not a malformed job, so it must produce a text-only job
    rather than an error that fails somebody's generation.
    """
    row = _row()
    assert "image_path" not in row
    assert Job.from_row(row).image_path is None


def test_the_reference_image_is_carried_through() -> None:
    assert Job.from_row(_row(image_path=REFERENCE)).image_path == REFERENCE


def test_a_blank_image_path_is_treated_as_absent() -> None:
    for blank in ("", "   ", None):
        assert Job.from_row(_row(image_path=blank)).image_path is None


def test_an_image_outside_the_owner_folder_is_rejected() -> None:
    """The path is the owner's folder by construction, so a row saying otherwise
    is not something to fetch on the strength of.

    `Job.from_row` raising is how `claim` marks a job `invalid_input` instead of
    acting on it, so this is a refusal rather than a crash.
    """
    stranger = UUID("99999999-0000-4000-8000-000000000009")
    with pytest.raises(ValueError, match="does not belong"):
        Job.from_row(_row(image_path=f"{stranger}/2026-09-05/photo.jpg"))


# --- SupabaseWorkerClient.download_reference ---------------------------------


class _Response:
    def __init__(self, payload: bytes, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def read(self, limit: int | None = None) -> bytes:
        return self._payload if limit is None else self._payload[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None


def _client(tmp_path: Path) -> tuple[SupabaseWorkerClient, AuthSession]:
    return SupabaseWorkerClient(_config(tmp_path)), AuthSession("token", WORKER, 1e9)


def test_the_reference_is_downloaded_to_the_destination(tmp_path, monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["auth"] = request.get_header("Authorization")
        return _Response(b"\xff\xd8\xff" + b"jpeg-bytes" * 40)

    monkeypatch.setattr(kaggle_worker.urllib.request, "urlopen", fake_urlopen)
    client, session = _client(tmp_path)
    destination = tmp_path / "nested" / "reference.jpg"

    client.download_reference(session, REFERENCE, destination)

    assert destination.read_bytes().startswith(b"\xff\xd8\xff")
    assert seen["method"] == "GET"
    assert seen["auth"] == "Bearer token"
    # The bucket is `uploads`, and every path segment is escaped rather than
    # pasted into a URL.
    assert str(seen["url"]).endswith(f"/storage/v1/object/uploads/{REFERENCE}")


def test_an_expired_lease_reads_as_an_http_error(tmp_path, monkeypatch) -> None:
    """RLS answers a lost lease with a refusal, and that must surface as one.

    `supabase/016` scopes the read to a live lease, so a worker that lingers
    past its lease gets HTTP 400 rather than somebody else's picture.
    """

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, None)

    monkeypatch.setattr(kaggle_worker.urllib.request, "urlopen", fake_urlopen)
    client, session = _client(tmp_path)

    with pytest.raises(RuntimeError, match="HTTP 400"):
        client.download_reference(session, REFERENCE, tmp_path / "ref.jpg")

    assert not (tmp_path / "ref.jpg").exists()


def test_an_empty_object_is_refused(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        kaggle_worker.urllib.request, "urlopen", lambda r, timeout=None: _Response(b"")
    )
    client, session = _client(tmp_path)

    with pytest.raises(RuntimeError, match="empty"):
        client.download_reference(session, REFERENCE, tmp_path / "ref.jpg")


def test_an_oversized_object_is_refused_without_writing_it(tmp_path, monkeypatch) -> None:
    """A still is a photo. Anything past the cap is refused before it lands.

    The read asks for one byte past the limit so an oversized object is caught
    rather than streamed onto the Kaggle box in full.
    """
    oversized = b"x" * (kaggle_worker.REFERENCE_MAX_BYTES + 1)
    monkeypatch.setattr(
        kaggle_worker.urllib.request, "urlopen", lambda r, timeout=None: _Response(oversized)
    )
    client, session = _client(tmp_path)

    with pytest.raises(RuntimeError, match="exceeds"):
        client.download_reference(session, REFERENCE, tmp_path / "ref.jpg")

    assert not (tmp_path / "ref.jpg").exists()


def test_the_worker_still_cannot_write_a_reference(tmp_path) -> None:
    """Read-only is the whole point: 016 adds no write surface.

    The client gained a download for `uploads`; the only uploads it can perform
    there remain the thumbnail, whose path shape is what migration 015's write
    predicate matches.
    """
    client, _ = _client(tmp_path)
    uploaders = [name for name in dir(client) if name.startswith("upload_")]

    assert sorted(uploaders) == ["upload_thumbnail", "upload_video"]
    assert (
        kaggle_worker.thumbnail_path(Job(PROJECT, USER, "a paper dragon", 4, "16:9"))
        == f"{USER}/{PROJECT}/thumbnail.jpg"
    )


def test_a_path_segment_is_escaped_rather_than_pasted_into_the_url(tmp_path, monkeypatch) -> None:
    """Object names come from the database, so they are data, not URL syntax.

    A `#` would otherwise truncate the request at a fragment and fetch the
    wrong object; the separators between segments must survive as separators.
    """
    seen: dict[str, str] = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        return _Response(b"jpeg" * 40)

    monkeypatch.setattr(kaggle_worker.urllib.request, "urlopen", fake_urlopen)
    client, session = _client(tmp_path)

    client.download_reference(session, f"{USER}/2026-09-05/a b#c.jpg", tmp_path / "ref.jpg")

    assert seen["url"].endswith(f"/uploads/{USER}/2026-09-05/a%20b%23c.jpg")
