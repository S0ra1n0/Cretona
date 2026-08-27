from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.credit_service import CreditService, iso
from app.errors import AppError
from app.repository import UnknownUserError

# No real money moves (ADR-010). Recorded on every row so the database itself
# discloses the simulation rather than leaving it to a document.
SIMULATED = "simulated"


class PaymentService:
    """Credit packages and the simulated purchase flow.

    §2.2 of the brief requires a way to buy credits, §3 an admin package API
    and a revenue figure, and §5 the `Credit Packages` and `Payments` tables.
    All of that is real. The one thing stubbed is the gateway confirmation --
    see ADR-010, and `payments.method`, which records `simulated` on every row.
    """

    def __init__(self, database: Any, credits: CreditService) -> None:
        self.database = database
        self.credits = credits

    def list_packages(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        return self.database.list_credit_packages(active_only=active_only)

    def purchase(
        self,
        user_id: str,
        package_id: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        """Buy a package. Returns the payment, with the new balance attached.

        A replayed `Idempotency-Key` returns the original payment and grants
        nothing further, which is what makes a retry after a dropped response
        safe rather than expensive.
        """
        if idempotency_key:
            existing = self.database.find_payment_by_key(user_id, idempotency_key)
            if existing is not None:
                return self._with_balance(user_id, existing)

        package = self.database.get_credit_package(package_id)
        if package is None:
            raise AppError(404, "NOT_FOUND", "That credit package does not exist.")

        if not package.get("is_active", True):
            # Listed a moment ago, withdrawn since. The app refreshes rather
            # than showing a price that is no longer offered.
            raise AppError(
                409,
                "PACKAGE_INACTIVE",
                "That package is no longer available. Refresh and try again.",
            )

        try:
            payment, _ = self.database.record_payment(
                payment_id=str(uuid4()),
                transaction_id=str(uuid4()),
                user_id=user_id,
                package_id=package["id"],
                amount_vnd=int(package["price_vnd"]),
                credits_granted=int(package["credits"]),
                method=SIMULATED,
                idempotency_key=idempotency_key,
                created_at=iso(datetime.now(UTC)),
            )
        except UnknownUserError:
            raise AppError(404, "NOT_FOUND", "Account not found.") from None

        return self._with_balance(user_id, payment)

    def _with_balance(self, user_id: str, payment: dict[str, Any]) -> dict[str, Any]:
        """The response carries the resulting balance so the app need not re-ask.

        A purchase screen that has to make a second call to learn the new
        balance shows a stale number for as long as that call takes.
        """
        enriched = dict(payment)
        enriched["balance"] = self.credits.balance(user_id)
        return enriched
