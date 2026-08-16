from __future__ import annotations

import os
from urllib.parse import urlsplit

# Hosts a disposable test database is allowed to live on. This is an allowlist,
# not a blocklist of known-production hosts: a blocklist fails open for every
# remote host nobody thought to add, which is the wrong direction for a guard
# whose failure mode is destroying real data.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})

ALLOW_REMOTE_VAR = "CRETONA_TEST_DATABASE_ALLOW_REMOTE"


class UnsafeTestDatabaseError(RuntimeError):
    """The configured test database is not safe to destroy."""


def assert_disposable_database(url: str) -> None:
    """Refuse to run the destructive Postgres fixture against a real database.

    tests/postgres_schema.sql drops and recreates public.video_projects,
    public.users, and public.roles. CRETONA_TEST_DATABASE_URL and the
    application's CRETONA_DATABASE_URL are one word apart, so a typo could point
    the test suite at production. Raising here is deliberately loud: a silent
    skip would let someone believe the parity suite ran when it did not.
    """
    host = (urlsplit(url).hostname or "").lower()

    if host in LOCAL_HOSTS:
        return

    if os.environ.get(ALLOW_REMOTE_VAR) == "1":
        return

    raise UnsafeTestDatabaseError(
        f"Refusing to run the destructive Postgres fixture against host {host!r}. "
        "tests/postgres_schema.sql DROPs public.video_projects, public.users, and "
        "public.roles. Point CRETONA_TEST_DATABASE_URL at a disposable local database "
        f"(one of: {', '.join(sorted(LOCAL_HOSTS))}), or set {ALLOW_REMOTE_VAR}=1 if this "
        "host is genuinely disposable. Never set it for a Supabase project."
    )
