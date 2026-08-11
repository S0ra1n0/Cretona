from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from threading import Lock
from time import monotonic

WINDOW_SECONDS = 60.0

# Generation costs money and provider time, so it gets a tighter bucket than
# ordinary reads. Rate limiting is burst protection; the quota is the actual
# spend control (ADR-007).
GENERATION_PATHS = ("/projects",)


class RateLimiter:
    """Fixed-cost sliding window, held in memory.

    In-memory means per-process: two instances behind a load balancer each
    permit the configured rate, so this bounds bursts rather than enforcing a
    global ceiling. That is the correct trade only because the quota, which is
    database-backed, is what protects the budget.
    """

    def __init__(self, *, default_per_minute: int, generation_per_minute: int) -> None:
        self.default_per_minute = default_per_minute
        self.generation_per_minute = generation_per_minute
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, bucket: str, now: float | None = None) -> tuple[bool, int, int]:
        """Return (allowed, limit, remaining) and record the hit if allowed."""
        moment = monotonic() if now is None else now
        limit = self.generation_per_minute if bucket == "generation" else self.default_per_minute

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

    The token is hashed rather than kept: this map outlives any single request,
    and a bearer token sitting in process memory keyed by itself is an
    unnecessary place for one to leak from.
    """
    if authorization:
        return "t:" + hashlib.sha256(authorization.encode()).hexdigest()[:32]
    if debug_user_id:
        return f"u:{debug_user_id}"
    return f"h:{client_host}"
