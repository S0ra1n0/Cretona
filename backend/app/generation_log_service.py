from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from app.logging_setup import redact

LogEvent = Literal["submit", "poll", "webhook", "download", "error"]

logger = logging.getLogger("cretona.generation_log")


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class RetentionSummary:
    """Non-sensitive aggregate emitted before raw audit rows disappear."""

    cutoff: str
    deleted: int
    by_provider: dict[str, int]
    by_event: dict[str, int]
    by_http_status: dict[str, int]
    batch_full: bool
    failed: bool = False


class GenerationLogRepository(Protocol):
    """Persistence boundary shared by SQLite and Supabase/Postgres."""

    def record_generation_log(self, values: dict[str, Any]) -> None: ...

    def prune_generation_logs(self, before: str, limit: int) -> list[dict[str, Any]]: ...


class GenerationLogService:
    """Provider interaction audit trail (P3-5).

    Without this a failed generation leaves nothing to debug: the user sees a
    safe message and the operator sees nothing at all.
    """

    def __init__(self, database: GenerationLogRepository) -> None:
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

    def prune(
        self,
        *,
        retention_days: int,
        batch_size: int,
        now: datetime | None = None,
    ) -> RetentionSummary:
        """Aggregate metadata and remove one expired batch, best effort.

        Durable storage for this aggregate is intentionally delegated to the
        structured-log pipeline (B-7). This service never selects or logs the
        raw request and response columns.
        """
        cutoff = _iso((now or datetime.now(UTC)) - timedelta(days=retention_days))
        try:
            rows = self.database.prune_generation_logs(cutoff, batch_size)
        except Exception:
            logger.warning(
                "generation_log_prune_failed",
                extra={"cutoff": cutoff, "batchSize": batch_size},
            )
            return RetentionSummary(cutoff, 0, {}, {}, {}, False, failed=True)

        providers = Counter(str(row["provider"]) for row in rows)
        events = Counter(str(row["event"]) for row in rows)
        statuses = Counter(
            "none" if row.get("http_status") is None else str(row["http_status"]) for row in rows
        )
        summary = RetentionSummary(
            cutoff=cutoff,
            deleted=len(rows),
            by_provider=dict(sorted(providers.items())),
            by_event=dict(sorted(events.items())),
            by_http_status=dict(sorted(statuses.items())),
            batch_full=len(rows) == batch_size,
        )
        logger.info(
            "generation_logs_pruned",
            extra={
                "cutoff": summary.cutoff,
                "deleted": summary.deleted,
                "batchFull": summary.batch_full,
                "byProvider": summary.by_provider,
                "byEvent": summary.by_event,
                "byHttpStatus": summary.by_http_status,
            },
        )
        return summary
