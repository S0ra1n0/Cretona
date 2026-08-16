from __future__ import annotations

import pytest

from tests.db_safety import ALLOW_REMOTE_VAR, UnsafeTestDatabaseError, assert_disposable_database

LOCAL_URL = "postgresql://postgres:pw@127.0.0.1:55432/cretona"
SUPABASE_URL = "postgresql://postgres:pw@db.abcdefghijkl.supabase.co:5432/postgres"
POOLER_URL = "postgresql://postgres.abc:pw@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"


@pytest.mark.parametrize(
    "url",
    [
        LOCAL_URL,
        "postgresql://postgres:pw@localhost:5432/cretona",
        "postgresql://postgres:pw@host.docker.internal:5432/cretona",
    ],
)
def test_local_targets_are_allowed(url: str) -> None:
    assert_disposable_database(url)


@pytest.mark.parametrize("url", [SUPABASE_URL, POOLER_URL])
def test_supabase_targets_are_refused(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ALLOW_REMOTE_VAR, raising=False)

    with pytest.raises(UnsafeTestDatabaseError, match="Refusing to run"):
        assert_disposable_database(url)


def test_unknown_remote_host_is_refused_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # The guard is an allowlist, so a host nobody anticipated is still refused.
    monkeypatch.delenv(ALLOW_REMOTE_VAR, raising=False)

    with pytest.raises(UnsafeTestDatabaseError):
        assert_disposable_database("postgresql://user:pw@db.internal.example.com:5432/app")


def test_remote_target_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ALLOW_REMOTE_VAR, "1")

    assert_disposable_database(SUPABASE_URL)


def test_opt_in_must_be_exactly_one(monkeypatch: pytest.MonkeyPatch) -> None:
    # A truthy-looking value is not enough; the escape hatch is deliberate.
    monkeypatch.setenv(ALLOW_REMOTE_VAR, "true")

    with pytest.raises(UnsafeTestDatabaseError):
        assert_disposable_database(SUPABASE_URL)


def test_the_error_names_what_would_be_destroyed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ALLOW_REMOTE_VAR, raising=False)

    with pytest.raises(UnsafeTestDatabaseError) as caught:
        assert_disposable_database(SUPABASE_URL)

    message = str(caught.value)
    assert "video_projects" in message
    assert ALLOW_REMOTE_VAR in message
