from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.credit_service import iso
from app.errors import AppError
from app.repository import AuditEntry, InsufficientCreditsError, UnknownUserError

# Settings an admin may change through the API. A whitelist rather than a
# free-form key/value write: `settings` is read by the charge path, and an
# admin who could invent keys could also shadow one.
EDITABLE_SETTINGS = {"generation_cost_credits"}


def _entry(
    *, actor_id: str, action: str, target_type: str, target_id: str | None,
    details: dict[str, Any],
) -> AuditEntry:
    return AuditEntry(
        id=str(uuid.uuid4()),
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        created_at=iso(datetime.now(UTC)),
    )


class AdminCreditService:
    """Admin control over credits, packages, events and the generation cost.

    §3 of the brief: an admin adds and subtracts credits, configures what a
    generation costs, manages packages, and creates promotions with a window,
    a grant and a registration cap.

    Every mutation here is audit-logged, and the credit adjustment writes its
    trail inside the same transaction as the money -- an adjustment that
    happened with no record of who made it is the gap T2-5 closed for the rest
    of the admin surface.
    """

    def __init__(self, database: Any, credits: Any) -> None:
        self.database = database
        self.credits = credits

    # --- credits -------------------------------------------------------------

    def adjust(
        self, actor_id: str, target_id: str, delta: int, note: str | None
    ) -> dict[str, Any]:
        if delta == 0:
            raise AppError(
                400,
                "VALIDATION_ERROR",
                "An adjustment must add or remove credits.",
                [{"field": "delta", "issue": "must_not_be_zero"}],
            )

        audit = _entry(
            actor_id=actor_id,
            action="credits.adjust",
            target_type="user",
            target_id=target_id,
            details={"delta": delta, "note": note},
        )

        try:
            if delta > 0:
                row, _ = self.credits.grant(
                    target_id, delta, reason="admin_adjustment",
                    note=note, audit=audit,
                )
            else:
                row, _ = self.credits.charge(
                    target_id, -delta, reason="admin_adjustment",
                    note=note, audit=audit,
                )
        except InsufficientCreditsError:  # pragma: no cover - charge maps this
            raise AppError(
                409, "CONFLICT", "That would leave a negative balance."
            ) from None
        except UnknownUserError:
            raise AppError(404, "NOT_FOUND", "Account not found.") from None

        return {
            "userId": target_id,
            "delta": row["delta"],
            "balance": row["balance_after"],
            "transactionId": str(row["id"]),
        }

    def transactions(
        self,
        *,
        user_id: str | None,
        reason: str | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if user_id:
            return self.database.list_credit_transactions(
                user_id, limit=limit, cursor=cursor, reason=reason
            )
        return self.database.list_all_credit_transactions(
            limit=limit, cursor=cursor, reason=reason
        )

    # --- settings ------------------------------------------------------------

    def settings(self) -> dict[str, str]:
        return {
            key: self.database.get_setting(key) or ""
            for key in sorted(EDITABLE_SETTINGS)
        }

    def update_setting(self, actor_id: str, key: str, value: str) -> dict[str, str]:
        if key not in EDITABLE_SETTINGS:
            raise AppError(
                400,
                "VALIDATION_ERROR",
                f"'{key}' is not a configurable setting.",
                [{"field": "key", "issue": "not_editable"}],
            )
        if key == "generation_cost_credits":
            try:
                cost = int(value)
            except (TypeError, ValueError):
                cost = 0
            if cost < 1:
                raise AppError(
                    400,
                    "VALIDATION_ERROR",
                    "The generation cost must be at least 1 credit.",
                    [{"field": "value", "issue": "must_be_positive"}],
                )

        previous = self.database.get_setting(key)
        self.database.set_setting(
            key, value, updated_by=actor_id, updated_at=iso(datetime.now(UTC))
        )
        # No transaction to join here: `set_setting` has already committed, so
        # this follows it rather than riding along, which is the same trade-off
        # AdminService._audit documents for the backfill.
        self.database.insert_audit_log(
            id=str(uuid.uuid4()),
            actor_id=actor_id,
            action="settings.update",
            target_type="setting",
            target_id=key,
            details={"from": previous, "to": value},
            created_at=iso(datetime.now(UTC)),
        )
        return self.settings()

    # --- packages ------------------------------------------------------------

    def packages(self) -> list[dict[str, Any]]:
        return self.database.list_credit_packages(active_only=False)

    def create_package(self, actor_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        package = self.database.create_credit_package(
            package_id=str(uuid.uuid4()),
            name=payload["name"],
            credits=payload["credits"],
            price_vnd=payload["price_vnd"],
            sort_order=payload.get("sort_order", 0),
            created_at=iso(datetime.now(UTC)),
            audit=_entry(
                actor_id=actor_id,
                action="package.create",
                target_type="credit_package",
                target_id=None,
                details=payload,
            ),
        )
        return package

    def update_package(
        self, actor_id: str, package_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        if not changes:
            raise AppError(400, "VALIDATION_ERROR", "Nothing to change.")
        updated = self.database.update_credit_package(
            package_id,
            changes,
            audit=_entry(
                actor_id=actor_id,
                action="package.update",
                target_type="credit_package",
                target_id=package_id,
                details=changes,
            ),
        )
        if updated is None:
            raise AppError(404, "NOT_FOUND", "That package does not exist.")
        return updated

    # --- events --------------------------------------------------------------

    def events(self) -> list[dict[str, Any]]:
        return self.database.list_events(active_only=False)

    def create_event(self, actor_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._validate_event(payload)
        return self.database.create_event(
            event_id=str(uuid.uuid4()),
            values=payload,
            created_at=iso(datetime.now(UTC)),
            audit=_entry(
                actor_id=actor_id,
                action="event.create",
                target_type="event",
                target_id=None,
                details={"code": payload.get("code"), "kind": payload.get("kind")},
            ),
        )

    def update_event(
        self, actor_id: str, event_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        if not changes:
            raise AppError(400, "VALIDATION_ERROR", "Nothing to change.")
        updated = self.database.update_event(
            event_id,
            changes,
            audit=_entry(
                actor_id=actor_id,
                action="event.update",
                target_type="event",
                target_id=event_id,
                details=changes,
            ),
        )
        if updated is None:
            raise AppError(404, "NOT_FOUND", "That event does not exist.")
        return updated

    def claims(self, event_id: str) -> list[dict[str, Any]]:
        if self.database.get_event(event_id) is None:
            raise AppError(404, "NOT_FOUND", "That event does not exist.")
        return self.database.list_event_claims(event_id)

    @staticmethod
    def _validate_event(payload: dict[str, Any]) -> None:
        """Reject the shapes the database would reject, with a usable message.

        The CHECK constraints already refuse a grant with no credits or a
        discount that also grants. Repeating them here is not duplication for
        its own sake: an admin filling in a form deserves to be told which
        field is wrong, not to receive a constraint violation.
        """
        kind = payload.get("kind")
        if kind == "grant" and not payload.get("bonus_credits"):
            raise AppError(
                400,
                "VALIDATION_ERROR",
                "A grant event needs the number of credits it gives.",
                [{"field": "bonusCredits", "issue": "required_for_grant"}],
            )
        if kind == "discount" and not payload.get("discount_percent"):
            raise AppError(
                400,
                "VALIDATION_ERROR",
                "A discount event needs a percentage.",
                [{"field": "discountPercent", "issue": "required_for_discount"}],
            )
        starts, ends = payload.get("starts_at"), payload.get("ends_at")
        if starts and ends and str(ends) <= str(starts):
            raise AppError(
                400,
                "VALIDATION_ERROR",
                "The event must end after it starts.",
                [{"field": "endsAt", "issue": "before_start"}],
            )

    # --- payments ------------------------------------------------------------

    def payments(
        self, *, status: str | None, limit: int, cursor: str | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        return self.database.list_payments(status=status, limit=limit, cursor=cursor)
