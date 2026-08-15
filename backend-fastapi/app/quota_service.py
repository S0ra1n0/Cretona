from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import Settings
from app.errors import AppError
from app.schemas import Quota

# Failures that were our problem, not the user's, and so do not consume an
# allowance. `content_policy` is deliberately absent: the provider call was
# made and billed, so it counts (ADR-007).
NOT_CHARGED = ("provider_error", "timeout", "cancelled")


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


class QuotaService:
    """The spend control (ADR-007).

    Rate limiting protects against bursts; only this protects the budget,
    because a few requests per minute is still thousands of paid generations
    a day.
    """

    def __init__(self, database: Any, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    @property
    def window(self) -> timedelta:
        return timedelta(hours=self.settings.generation_quota_window_hours)

    def get(self, user_id: str, now: datetime | None = None) -> Quota:
        moment = now or datetime.now(UTC)
        # Counting rows rather than maintaining a counter column: there is no
        # counter to drift out of sync and no reconciliation job.
        used, oldest = self.database.count_quota_usage(
            user_id,
            iso(moment - self.window),
            NOT_CHARGED,
        )

        limit = self.settings.generation_quota_limit
        # When the oldest counted generation ages out, a slot frees up. With
        # nothing counted there is nothing to free, so report a full window.
        anchor = _parse(oldest) or moment
        return Quota(
            limit=limit,
            used=used,
            remaining=max(0, limit - used),
            resetsAt=iso(anchor + self.window),
        )

    def assert_available(self, user_id: str, cost: int = 1) -> Quota:
        """Call before any provider request.

        Checking afterwards is accounting, not control: it would not prevent
        the spend that already happened.
        """
        quota = self.get(user_id)
        if quota.remaining < cost:
            raise AppError(
                429,
                "QUOTA_EXCEEDED",
                f"You have used all {quota.limit} generations for this period. "
                f"More become available at {quota.resets_at}.",
            )
        return quota


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
