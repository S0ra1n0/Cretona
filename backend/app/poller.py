from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


logger = logging.getLogger("cretona.poller")


class JobPoller:
    """Advances in-flight generations without waiting for a client to ask.

    Reading a project also advances it, which is enough for a demo where the
    app polls. It is not enough in general: a job whose client disconnects
    would sit at `generating` forever, holding quota and never completing.
    """

    def __init__(
        self,
        database: Any,
        project_service: Any,
        settings: Any,
        providers: Any = None,
    ) -> None:
        self.database = database
        self.project_service = project_service
        self.settings = settings
        # W1: claim only what this process can actually advance. Without it the
        # poller and an external worker fight over the same rows.
        self.claimable_providers: tuple[str, ...] | None = (
            tuple(providers.in_process_names()) if providers is not None else None
        )
        # Identifies this instance's claims. Regenerated per process, so a
        # restarted poller does not inherit its own stale leases -- it waits
        # for them to expire like any other holder would.
        self.instance_id = f"poller-{uuid4()}"
        self._task: asyncio.Task[None] | None = None

    def run_once(self) -> int:
        """Advance one leased batch. Returns how many projects were touched."""
        now = datetime.now(UTC)
        rows = self.database.claim_in_flight_projects(
            self.settings.poll_batch_size,
            owner=self.instance_id,
            now=_iso(now),
            lease_until=_iso(now + timedelta(seconds=self.settings.poll_lease_seconds)),
            providers=self.claimable_providers,
        )
        advanced = 0

        for row in rows:
            try:
                self.project_service.advance(row)
                advanced += 1
            except Exception:
                # One poisoned project must not stop the batch, or a single bad
                # row would stall every other generation on the system.
                logger.warning(
                    "poll_failed",
                    extra={"projectId": row.get("id"), "provider": row.get("provider")},
                )
            finally:
                # Released even when advancing failed, so a transient error
                # does not hold the row hostage for the whole lease.
                self._release(row)
        return advanced

    def _release(self, row: dict[str, Any]) -> None:
        try:
            self.database.release_lease(row["id"], self.instance_id)
        except Exception:
            # The lease expires on its own, so a failed release costs a delay
            # rather than the row.
            logger.warning("lease_release_failed", extra={"projectId": row.get("id")})

    async def run_forever(self) -> None:
        interval = self.settings.poll_interval_seconds
        while True:
            try:
                # The adapters are blocking, so the batch runs off the event
                # loop rather than stalling every request while it works.
                await asyncio.to_thread(self.run_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("poll_batch_failed")
            await asyncio.sleep(interval)

    @property
    def is_running(self) -> bool:
        return self._task is not None

    def start(self) -> None:
        if self.settings.poller_enabled and self._task is None:
            self._task = asyncio.create_task(self.run_forever())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        # Shutdown must not raise, whether the task was cancelled cleanly or
        # died of something else on its way out.
        with contextlib.suppress(BaseException):
            await self._task
        self._task = None
