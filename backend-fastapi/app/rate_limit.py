from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from typing import Protocol

WINDOW_SECONDS = 60.0

# Generation costs money and provider time, so it gets a tighter bucket than
# ordinary reads. Rate limiting is burst protection; the quota is the actual
# spend control (ADR-007).
GENERATION_PATHS = ("/projects",)


class SharedRateLimitStore(Protocol):
    """Persistence boundary for a limiter shared by several API instances."""

    def consume_rate_limit(
        self,
        key: str,
        bucket: str,
        limit: int,
        window_seconds: float,
    ) -> tuple[bool, int]: ...


class RateLimiter:
    """Sliding-window limiter with a credential-free in-memory fallback.

    Postgres deployments inject a shared store so every API instance observes
    one window. SQLite keeps this process-local implementation because it is
    the zero-credential development profile, not a multi-instance deployment.
    """

    def __init__(
        self,
        *,
        default_per_minute: int,
        generation_per_minute: int,
        shared_store: SharedRateLimitStore | None = None,
    ) -> None:
        self.default_per_minute = default_per_minute
        self.generation_per_minute = generation_per_minute
        self._shared_store = shared_store
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, bucket: str, now: float | None = None) -> tuple[bool, int, int]:
        """Return (allowed, limit, remaining) and record the hit if allowed."""
        limit = self.generation_per_minute if bucket == "generation" else self.default_per_minute
        if self._shared_store is not None:
            if now is not None:
                raise ValueError("A shared rate limiter owns its database clock.")
            allowed, remaining = self._shared_store.consume_rate_limit(
                key,
                bucket,
                limit,
                WINDOW_SECONDS,
            )
            return allowed, limit, remaining

        moment = monotonic() if now is None else now

        with self._lock:
            hits = self._hits[(key, bucket)]
            cutoff = moment - WINDOW_SECONDS
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= limit:
                return False, limit, 0

            hits.append(moment)
            return True, limit, max(0, limit - len(hits))

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def bucket_for(method: str, path: str) -> str:
    if method == "POST" and any(segment in path for segment in GENERATION_PATHS):
        return "generation"
    return "default"


def caller_key(authorization: str | None, debug_user_id: str | None, client_host: str) -> str:
    """Identify the caller without storing a credential.

    Every source is hashed because the shared store outlives a request. That
    keeps bearer tokens, debug identities, and client IP addresses out of both
    process keys and persisted rows.
    """
    if authorization:
        prefix, source = "t:", authorization
    elif debug_user_id:
        prefix, source = "u:", debug_user_id
    else:
        prefix, source = "h:", client_host
    return prefix + hashlib.sha256(source.encode()).hexdigest()[:32]
