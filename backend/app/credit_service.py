from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.errors import AppError
from app.repository import InsufficientCreditsError, UnknownUserError

# Every reason a balance may move. Mirrors the CHECK constraint on
# credit_transactions.reason -- the database is the enforcement, this is the
# vocabulary the service speaks.
REASONS = (
    "signup_bonus",
    "event_grant",
    "purchase",
    "generation",
    "refund",
    "admin_adjustment",
)

SETTING_GENERATION_COST = "generation_cost_credits"
DEFAULT_GENERATION_COST = 1


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


class CreditService:
    """The only writer of a credit balance.

    Everything that moves credits goes through here: generation charges,
    refunds, event grants, purchases and admin adjustments. Concentrating it
    is what makes the invariants checkable -- a second writer somewhere else
    would make "the ledger explains the balance" untestable in practice.

    The service does not enforce the invariants itself. They live in the
    database: a non-negative balance is a WHERE clause, single-charge is a
    unique index, and atomicity is one transaction. A service-level check
    would lose to a concurrent request, and the thing it would lose is money.
    """

    def __init__(self, database: Any) -> None:
        self.database = database

    # --- reading -------------------------------------------------------------

    def balance(self, user_id: str) -> int:
        current = self.database.get_credit_balance(user_id)
        if current is None:
            raise AppError(404, "NOT_FOUND", "Account not found.")
        return current

    def totals(self, user_id: str) -> tuple[int, int]:
        """Lifetime granted and lifetime spent, both positive."""
        return self.database.credit_totals(user_id)

    def history(
        self,
        user_id: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
        reason: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        return self.database.list_credit_transactions(
            user_id, limit=limit, cursor=cursor, reason=reason
        )

    def generation_cost(self) -> int:
        """The configured base cost, before any discount event.

        Read from `settings` rather than config so an admin can change it
        without a redeploy -- §3 of the brief asks for exactly that. A missing
        or malformed row falls back rather than failing a generation: a broken
        setting should not take the product down.
        """
        raw = self.database.get_setting(SETTING_GENERATION_COST)
        if raw is None:
            return DEFAULT_GENERATION_COST
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return DEFAULT_GENERATION_COST
        return value if value > 0 else DEFAULT_GENERATION_COST

    @staticmethod
    def effective_cost(base_cost: int, discount_percent: int | None) -> int:
        """Cost after an active discount, floored at 1.

        Floored deliberately: a 100%-off event should still record that a
        generation happened and cost something, because a zero-delta row
        violates `delta <> 0` and would leave the generation unexplained in
        the ledger. Contract §10.2.
        """
        if not discount_percent:
            return max(1, base_cost)
        remaining = round(base_cost * (100 - discount_percent) / 100)
        return max(1, remaining)

    # --- writing -------------------------------------------------------------

    def grant(
        self,
        user_id: str,
        amount: int,
        *,
        reason: str,
        ref_type: str | None = None,
        ref_id: str | None = None,
        note: str | None = None,
        idempotency_key: str | None = None,
        audit: Any = None,
    ) -> tuple[dict[str, Any], bool]:
        if amount <= 0:
            raise ValueError("A grant must be positive; use charge() to deduct.")
        return self._apply(
            user_id,
            amount,
            reason=reason,
            ref_type=ref_type,
            ref_id=ref_id,
            note=note,
            idempotency_key=idempotency_key,
            audit=audit,
        )

    def charge(
        self,
        user_id: str,
        amount: int,
        *,
        reason: str = "generation",
        ref_type: str | None = None,
        ref_id: str | None = None,
        note: str | None = None,
        idempotency_key: str | None = None,
        audit: Any = None,
    ) -> tuple[dict[str, Any], bool]:
        """Deduct credits, or raise 402 if the balance will not cover it.

        Call this *before* the provider request. Charging afterwards is
        accounting, not control -- the same reasoning ADR-007 gives for the
        quota check, and the reason a user with one credit cannot start ten
        jobs.
        """
        if amount <= 0:
            raise ValueError("A charge must be positive.")
        return self._apply(
            user_id,
            -amount,
            reason=reason,
            ref_type=ref_type,
            ref_id=ref_id,
            note=note,
            idempotency_key=idempotency_key,
            audit=audit,
        )

    def refund_for(
        self,
        user_id: str,
        *,
        ref_type: str,
        ref_id: str,
        note: str | None = None,
    ) -> dict[str, Any] | None:
        """Give back exactly what was charged for this reference.

        The amount is read back from the original charge rather than
        recomputed. A discount may have ended since, and recomputing would
        refund a different number from the one taken -- contract §10.4.

        Idempotent by construction: the refund carries a key derived from the
        reference, so a retried failure callback cannot refund twice. Returns
        None when there is nothing to refund, which is the normal case for a
        job that never got as far as being charged.
        """
        charge = self._find_charge(user_id, ref_type=ref_type, ref_id=ref_id)
        if charge is None:
            return None

        row, _ = self._apply(
            user_id,
            -int(charge["delta"]),  # the charge is negative, so this is positive
            reason="refund",
            ref_type=ref_type,
            ref_id=ref_id,
            note=note or f"Refund for {ref_type} {ref_id}",
            idempotency_key=f"refund:{ref_type}:{ref_id}",
        )
        return row

    def ensure_signup_bonus(self, user_id: str) -> int:
        """Apply the signup-bonus event once, if one is running.

        Section 2.1 of the brief: an ordinary account starts at 0 credits, and
        an account created during a valid promotion gets that promotion's
        credits. Without this a new user starts at zero and can never generate
        anything, because nothing else grants a first credit.

        Applied lazily, on the first profile read, rather than at signup. The
        row is created three different ways depending on the profile -- the
        Supabase trigger, the local sqlite provisioner, or a seed script -- and
        only two of those run any Python we control. Reading the profile is the
        one thing every client does after signing in, whichever created it.

        Idempotent on `signup:{user_id}`, so repeated reads grant once. Returns
        the credits granted, or 0.
        """
        event = self.database.find_auto_grant_event(iso(datetime.now(UTC)))
        if not event:
            return 0

        amount = int(event.get("bonus_credits") or 0)
        if amount <= 0:
            return 0

        _, created = self.grant(
            user_id,
            amount,
            reason="signup_bonus",
            ref_type="event",
            ref_id=str(event["id"]),
            note=event.get("name"),
            idempotency_key=f"signup:{user_id}",
        )
        return amount if created else 0

    # --- internals -----------------------------------------------------------

    def _find_charge(self, user_id: str, *, ref_type: str, ref_id: str) -> dict[str, Any] | None:
        """The charge for a reference, if it has not already been refunded.

        Paged rather than queried directly because the repository exposes the
        ledger as a list: at the volumes this project sees, a user's history is
        short, and a dedicated query would be a third method to keep in step
        across two adapters.
        """
        cursor: str | None = None
        charge: dict[str, Any] | None = None
        while True:
            rows, cursor = self.database.list_credit_transactions(user_id, limit=100, cursor=cursor)
            for row in rows:
                if row.get("ref_type") != ref_type or row.get("ref_id") != ref_id:
                    continue
                if row["reason"] == "refund":
                    # Already refunded. Stop rather than refund again.
                    return None
                if int(row["delta"]) < 0 and charge is None:
                    charge = row
            if not cursor:
                return charge

    def _apply(
        self,
        user_id: str,
        delta: int,
        *,
        reason: str,
        ref_type: str | None,
        ref_id: str | None,
        note: str | None,
        idempotency_key: str | None,
        audit: Any = None,
    ) -> tuple[dict[str, Any], bool]:
        if reason not in REASONS:
            raise ValueError(f"Unknown credit reason: {reason}")
        try:
            return self.database.apply_credit_delta(
                transaction_id=str(uuid4()),
                user_id=user_id,
                delta=delta,
                reason=reason,
                created_at=iso(datetime.now(UTC)),
                ref_type=ref_type,
                ref_id=ref_id,
                note=note,
                idempotency_key=idempotency_key,
                audit=audit,
            )
        except InsufficientCreditsError:
            balance = self.database.get_credit_balance(user_id) or 0
            raise AppError(
                402,
                "INSUFFICIENT_CREDITS",
                f"This needs {abs(delta)} credits and you have {balance}. "
                "Claim an event reward or buy more credits to continue.",
            ) from None
        except UnknownUserError:
            raise AppError(404, "NOT_FOUND", "Account not found.") from None
