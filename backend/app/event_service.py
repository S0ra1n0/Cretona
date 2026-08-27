from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.credit_service import CreditService, iso
from app.errors import AppError
from app.repository import UnknownUserError

# Campaign windows are written in local Vietnam time, because that is what the
# people running them mean by "8pm to 10pm". Storage is UTC; only the
# minute-of-day and weekday comparisons happen here.
LOCAL = timezone(timedelta(hours=7), name="ICT")

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

GRANT = "grant"
DISCOUNT = "discount"


def _parse(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class EventService:
    """Campaign windows, claiming, and the discount that applies right now.

    One table serves grants and discounts because they differ only in payload:
    a grant gives credits when claimed, a discount lowers the price by itself.
    Splitting them would have duplicated the window, recurrence and cap logic
    that makes up most of this file.

    The service decides *whether* a window is open. It never decides whether a
    claim succeeds -- the cap and the one-per-period rule are enforced by the
    database, because a check here would lose to a second tap.
    """

    def __init__(self, database: Any, credits: CreditService) -> None:
        self.database = database
        self.credits = credits

    # --- window evaluation ---------------------------------------------------

    @staticmethod
    def period_key(event: dict[str, Any], moment: datetime) -> str:
        """The occurrence a claim belongs to.

        This is what makes "once per weekend" mean a weekend rather than
        forever: the unique index is on (event, user, period), so a new period
        is a new claim and the same period is a duplicate.
        """
        local = moment.astimezone(LOCAL)
        recurrence = event.get("recurrence", "once")
        if recurrence == "daily":
            return local.date().isoformat()
        if recurrence == "weekly":
            year, week, _ = local.isocalendar()
            return f"{year}-W{week:02d}"
        return ""

    @classmethod
    def is_active(cls, event: dict[str, Any], moment: datetime) -> bool:
        if not event.get("is_active", True):
            return False

        starts = _parse(event.get("starts_at"))
        ends = _parse(event.get("ends_at"))
        if starts is None or ends is None:
            return False
        if not (starts <= moment < ends):
            return False

        local = moment.astimezone(LOCAL)
        recurrence = event.get("recurrence", "once")

        if recurrence == "weekly":
            allowed = cls._weekdays(event)
            if allowed and WEEKDAYS[local.weekday()] not in allowed:
                return False

        return cls._within_minute_window(event, local)

    @staticmethod
    def _weekdays(event: dict[str, Any]) -> set[str]:
        raw = event.get("active_days") or ""
        return {part.strip().lower() for part in raw.split(",") if part.strip()}

    @staticmethod
    def _within_minute_window(event: dict[str, Any], local: datetime) -> bool:
        start = event.get("active_from_minute")
        end = event.get("active_to_minute")
        if start is None or end is None:
            return True

        minute = local.hour * 60 + local.minute
        if start <= end:
            return start <= minute < end
        # A window that wraps midnight -- 22:00 to 02:00 -- is two ranges, not
        # one. Without this it would never be open.
        return minute >= start or minute < end

    @classmethod
    def next_active_at(cls, event: dict[str, Any], moment: datetime) -> str | None:
        """When this event next opens, for a card that is not open yet.

        Scanned hour by hour over the campaign, capped at a week. Precise
        arithmetic per recurrence would be three more branches to get wrong,
        and this runs once per card on a screen a user opens by hand.
        """
        starts = _parse(event.get("starts_at"))
        ends = _parse(event.get("ends_at"))
        if starts is None or ends is None or moment >= ends:
            return None

        probe = max(moment, starts).replace(minute=0, second=0, microsecond=0)
        horizon = min(ends, moment + timedelta(days=8))
        while probe < horizon:
            if cls.is_active(event, probe):
                return iso(probe)
            probe += timedelta(hours=1)
        return None

    def active_until(self, event: dict[str, Any], moment: datetime) -> str | None:
        """When the current opening closes."""
        ends = _parse(event.get("ends_at"))
        start_minute = event.get("active_from_minute")
        end_minute = event.get("active_to_minute")
        if start_minute is None or end_minute is None:
            return iso(ends) if ends else None

        local = moment.astimezone(LOCAL)
        closing = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
            minutes=end_minute
        )
        if closing <= local:
            closing += timedelta(days=1)
        if ends and closing > ends:
            return iso(ends)
        return iso(closing)

    # --- discounts -----------------------------------------------------------

    def active_discount(self, moment: datetime | None = None) -> dict[str, Any] | None:
        """The discount running right now, or None.

        The deepest one wins if two overlap. Two live discounts is a
        configuration mistake, and the choice that never surprises a user is
        the cheaper price.
        """
        now = moment or datetime.now(UTC)
        candidates = [
            event
            for event in self.database.list_events()
            if event.get("kind") == DISCOUNT and self.is_active(event, now)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda event: event.get("discount_percent") or 0)

    def discount_percent(self, moment: datetime | None = None) -> int | None:
        event = self.active_discount(moment)
        return int(event["discount_percent"]) if event else None

    # --- listing -------------------------------------------------------------

    def list_for(self, user_id: str, moment: datetime | None = None) -> list[dict[str, Any]]:
        """Events with this caller's claim state resolved.

        `claimable` is computed here and nowhere else. The app binds its button
        straight to it rather than re-deriving it from the window, the cap and
        the claim history -- two implementations of that rule would eventually
        disagree, and the one that gives credits away is the client's.
        """
        now = moment or datetime.now(UTC)
        events = self.database.list_events()
        claimed = self.database.claimed_periods(
            user_id, [event["id"] for event in events]
        )

        out: list[dict[str, Any]] = []
        for event in events:
            active = self.is_active(event, now)
            period = self.period_key(event, now)
            already = (event["id"], period) in claimed

            remaining: int | None = None
            if event.get("max_claims") is not None:
                remaining = max(
                    0,
                    int(event["max_claims"]) - self.database.count_event_claims(event["id"]),
                )

            claimable = (
                event.get("kind") == GRANT
                and active
                and not already
                and not event.get("auto_grant")
                and (remaining is None or remaining > 0)
            )

            out.append(
                {
                    **event,
                    "is_active_now": active,
                    "active_until": self.active_until(event, now) if active else None,
                    "next_active_at": None if active else self.next_active_at(event, now),
                    "claimable": claimable,
                    "claimed_this_period": already,
                    "remaining_slots": remaining,
                }
            )
        return out

    # --- claiming ------------------------------------------------------------

    def claim(self, user_id: str, event_id: str, moment: datetime | None = None) -> dict[str, Any]:
        now = moment or datetime.now(UTC)
        event = self.database.get_event(event_id)
        if event is None:
            raise AppError(404, "NOT_FOUND", "That event does not exist.")

        if event.get("kind") != GRANT:
            raise AppError(
                409,
                "EVENT_NOT_ACTIVE",
                "This discount applies automatically; there is nothing to claim.",
            )

        if event.get("auto_grant"):
            raise AppError(
                409,
                "EVENT_NOT_ACTIVE",
                "This reward is applied automatically.",
            )

        if not self.is_active(event, now):
            raise AppError(
                409, "EVENT_NOT_ACTIVE", "This event is not running right now."
            )

        try:
            row, status = self.database.claim_event(
                claim_id=str(uuid4()),
                transaction_id=str(uuid4()),
                event_id=event["id"],
                user_id=user_id,
                period_key=self.period_key(event, now),
                credits_granted=int(event["bonus_credits"]),
                max_claims=event.get("max_claims"),
                created_at=iso(now),
            )
        except UnknownUserError:
            raise AppError(404, "NOT_FOUND", "Account not found.") from None

        if status == "already":
            raise AppError(
                409, "EVENT_ALREADY_CLAIMED", "You have already claimed this reward."
            )
        if status == "full":
            raise AppError(
                409, "EVENT_FULL", "This event has been fully claimed."
            )

        assert row is not None
        return {
            "credits_granted": int(row["credits_granted"]),
            "balance": self.credits.balance(user_id),
            "transaction_id": str(row["id"]),
        }
