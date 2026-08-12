from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

logger = logging.getLogger("cretona.generation_log_retention")


class GenerationLogRetentionWorker:
    """Runs the bounded generation-log retention policy independently."""

    def __init__(self, service: Any, settings: Any) -> None:
        self.service = service
        self.settings = settings
        self._task: asyncio.Task[None] | None = None

    def run_once(self) -> Any:
        return self.service.prune(
            retention_days=self.settings.generation_log_retention_days,
            batch_size=self.settings.generation_log_retention_batch_size,
        )

    async def run_forever(self) -> None:
        interval = self.settings.generation_log_retention_interval_seconds
        while True:
            try:
                # Both adapters are synchronous. Keeping cleanup off the event
                # loop prevents a large batch from delaying user requests.
                await asyncio.to_thread(self.run_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                # The service already handles database failures, but the loop
                # is fenced too so an unexpected bug cannot kill maintenance
                # permanently.
                logger.warning("generation_log_retention_batch_failed")
            await asyncio.sleep(interval)

    @property
    def is_running(self) -> bool:
        return self._task is not None

    def start(self) -> None:
        if self.settings.generation_log_retention_enabled and self._task is None:
            self._task = asyncio.create_task(self.run_forever())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(BaseException):
            await self._task
        self._task = None
