from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

logger = logging.getLogger("cretona.poller")


class JobPoller:
    """Advances in-flight generations without waiting for a client to ask.

    Reading a project also advances it, which is enough for a demo where the
    app polls. It is not enough in general: a job whose client disconnects
    would sit at `generating` forever, holding quota and never completing.
    """

    def __init__(self, database: Any, project_service: Any, settings: Any) -> None:
        self.database = database
        self.project_service = project_service
        self.settings = settings
        self._task: asyncio.Task[None] | None = None

    def run_once(self) -> int:
        """Advance one batch. Returns how many projects were touched."""
        rows = self.database.claim_in_flight_projects(self.settings.poll_batch_size)
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
        return advanced

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
