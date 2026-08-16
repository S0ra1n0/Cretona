from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

# How long a fetched key set is trusted before a background-free refetch. Keys
# rotate rarely, so this is about bounding staleness, not performance.
DEFAULT_TTL_SECONDS = 600.0

# Floor between fetches triggered by an unknown `kid`. Without it, a stream of
# tokens carrying junk kids would turn into a request flood against the auth
# server -- an easy amplification vector on an endpoint anyone can reach.
MIN_REFETCH_INTERVAL_SECONDS = 30.0


class JwksError(Exception):
    """The key set could not be fetched or did not contain the key."""


class JwksCache:
    """Fetches and caches a Supabase JWKS, keyed by `kid`.

    Asymmetric verification needs the project's public keys, which are served
    over HTTP and rotate. Caching keeps a per-request network call off the auth
    path; refetching on an unknown `kid` is what makes rotation survivable
    without a restart.
    """

    def __init__(
        self,
        url: str,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        timeout_seconds: float = 5.0,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.url = url
        self.ttl_seconds = ttl_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)
        # One clock for the whole cache. Taking a per-call `now` while seeding
        # timestamps from the real monotonic clock makes the two incomparable,
        # and every staleness decision meaningless.
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: dict[str, dict[str, Any]] = {}
        self._fetched_at = float("-inf")
        self._last_attempt = float("-inf")

    def key_for(self, kid: str) -> dict[str, Any]:
        moment = self._clock()

        with self._lock:
            fresh = moment - self._fetched_at < self.ttl_seconds
            if fresh and kid in self._keys:
                return self._keys[kid]

            # Either the cache is stale, or it is fresh but lacks this kid --
            # which is what a rotation looks like from here.
            may_retry = moment - self._last_attempt >= MIN_REFETCH_INTERVAL_SECONDS
            if not fresh or may_retry:
                self._refresh(moment)

            key = self._keys.get(kid)
            if key is None:
                raise JwksError("Signing key is not published by the project.")
            return key

    def _refresh(self, moment: float) -> None:
        """Caller holds the lock."""
        self._last_attempt = moment
        try:
            response = self._client.get(self.url)
        except httpx.HTTPError as exc:
            raise JwksError("Could not reach the key set endpoint.") from exc

        if response.status_code >= 400:
            raise JwksError("The key set endpoint refused the request.")

        try:
            payload = response.json()
            keys = payload["keys"]
        except (ValueError, KeyError, TypeError) as exc:
            raise JwksError("The key set response was not usable.") from exc

        # Replaced wholesale rather than merged: a key withdrawn by the project
        # must stop verifying here too, and merging would keep it alive.
        self._keys = {
            key["kid"]: key
            for key in keys
            if isinstance(key, dict) and isinstance(key.get("kid"), str)
        }
        self._fetched_at = moment
