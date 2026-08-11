from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from app.logging_setup import redact

LogEvent = Literal["submit", "poll", "webhook", "download", "error"]

logger = logging.getLogger("cretona.generation_log")


class GenerationLogService:
    """Provider interaction audit trail (P3-5).

    Without this a failed generation leaves nothing to debug: the user sees a
    safe message and the operator sees nothing at all.
    """

    def __init__(self, database: Any) -> None:
        self.database = database

    def record(
        self,
        *,
        project_id: str,
        provider: str,
        event: LogEvent,
        request_id: str | None = None,
        request: Any = None,
        response: Any = None,
        http_status: int | None = None,
    ) -> None:
        try:
            self.database.record_generation_log(
                {
                    "project_id": project_id,
                    "provider": provider,
                    "request_id": request_id,
                    "event": event,
                    # Redacted at the source. A provider payload can carry an
                    # API key or a signed URL, and this table is long-lived.
                    "request": redact(request),
                    "response": redact(response),
                    "http_status": http_status,
                    "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                }
            )
        except Exception:
            # Best effort. Failing a generation because its audit row could not
            # be written would trade a working feature for a diagnostic.
            logger.warning(
                "generation_log_write_failed",
                extra={"projectId": project_id, "event": event},
            )
