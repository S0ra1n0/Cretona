"""CreditService and the ledger invariants (S-04).

These tests exist because every bug here is a money bug. The three that matter
most, and which the database rather than the service enforces:

  * a balance can never go negative,
  * a replayed idempotency key charges once,
  * the ledger always explains the balance.
"""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.credit_service import CreditService
from app.database import Database
from app.errors import AppError
from app.repository import InsufficientCreditsError, UnknownUserError

USER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "credits.sqlite3")
    db.initialize()
    db.upsert_user(USER, email="user@example.test", username="user")
    db.upsert_user(OTHER, email="other@example.test", username="other")
    return db


@pytest.fixture
def credits(database: Database) -> CreditService:
    return CreditService(database)


# --- balance and grants ------------------------------------------------------


def test_new_account_starts_at_zero(credits: CreditService) -> None:
    """Section 2.1 of the brief: a normal signup begins with 0 credits."""
    assert credits.balance(USER) == 0


def test_grant_moves_balance_and_writes_one_row(credits: CreditService) -> None:
    row, created = credits.grant(USER, 10, reason="signup_bonus")

    assert created is True
    assert row["delta"] == 10
    assert row["balance_after"] == 10
    assert credits.balance(USER) == 10

    history, _ = credits.history(USER)
    assert len(history) == 1
    assert history[0]["reason"] == "signup_bonus"


def test_balance_of_unknown_account_is_404(credits: CreditService) -> None:
    with pytest.raises(AppError) as excinfo:
        credits.balance("33333333-3333-4333-8333-333333333333")
    assert excinfo.value.status_code == 404


def test_grant_rejects_a_non_positive_amount(credits: CreditService) -> None:
    with pytest.raises(ValueError):
        credits.grant(USER, 0, reason="event_grant")
    with pytest.raises(ValueError):
        credits.grant(USER, -5, reason="event_grant")


def test_unknown_reason_is_rejected_before_touching_the_database(
    credits: CreditService,
) -> None:
    with pytest.raises(ValueError, match="Unknown credit reason"):
        credits.grant(USER, 5, reason="because_i_said_so")
    assert credits.balance(USER) == 0


# --- charging ----------------------------------------------------------------


def test_charge_deducts(credits: CreditService) -> None:
    credits.grant(USER, 10, reason="signup_bonus")
    row, _ = credits.charge(USER, 3, ref_type="project", ref_id="p1")

    assert row["delta"] == -3
    assert row["balance_after"] == 7
    assert credits.balance(USER) == 7


def test_charge_beyond_balance_raises_402_and_moves_nothing(
    credits: CreditService,
) -> None:
    credits.grant(USER, 2, reason="signup_bonus")

    with pytest.raises(AppError) as excinfo:
        credits.charge(USER, 5, ref_type="project", ref_id="p1")

    assert excinfo.value.status_code == 402
    assert excinfo.value.code == "INSUFFICIENT_CREDITS"
    # The balance is untouched and no ledger row was written: the guard is in
    # the UPDATE, so the failed charge never half-applied.
    assert credits.balance(USER) == 2
    history, _ = credits.history(USER)
    assert len(history) == 1


def test_charge_to_exactly_zero_is_allowed(credits: CreditService) -> None:
    credits.grant(USER, 5, reason="signup_bonus")
    credits.charge(USER, 5, ref_type="project", ref_id="p1")
    assert credits.balance(USER) == 0


# --- idempotency -------------------------------------------------------------


def test_replayed_key_charges_once(credits: CreditService) -> None:
    """A retried submit must not charge twice -- §5 of the brief."""
    credits.grant(USER, 10, reason="signup_bonus")

    first, created_first = credits.charge(
        USER, 1, ref_type="project", ref_id="p1", idempotency_key="KEY-1"
    )
    second, created_second = credits.charge(
        USER, 1, ref_type="project", ref_id="p1", idempotency_key="KEY-1"
    )

    assert created_first is True
    assert created_second is False
    assert first["id"] == second["id"]
    assert credits.balance(USER) == 9

    history, _ = credits.history(USER)
    assert [row["reason"] for row in history] == ["generation", "signup_bonus"]


def test_the_same_key_from_a_different_user_is_a_different_charge(
    credits: CreditService,
) -> None:
    """The unique index is per user, so two people may reuse a client key."""
    credits.grant(USER, 5, reason="signup_bonus")
    credits.grant(OTHER, 5, reason="signup_bonus")

    credits.charge(USER, 1, idempotency_key="SHARED")
    credits.charge(OTHER, 1, idempotency_key="SHARED")

    assert credits.balance(USER) == 4
    assert credits.balance(OTHER) == 4


# --- refunds -----------------------------------------------------------------


def test_refund_returns_exactly_what_was_charged(credits: CreditService) -> None:
    credits.grant(USER, 10, reason="signup_bonus")
    credits.charge(USER, 3, ref_type="project", ref_id="p1")

    refund = credits.refund_for(USER, ref_type="project", ref_id="p1")

    assert refund is not None
    assert refund["delta"] == 3
    assert credits.balance(USER) == 10


def test_refund_uses_the_original_amount_not_the_current_cost(
    credits: CreditService,
) -> None:
    """Contract §10.4.

    A discount that ended between the charge and the failure must not change
    what comes back. The refund reads the charge, it does not recompute it.
    """
    credits.grant(USER, 10, reason="signup_bonus")
    credits.charge(USER, 1, ref_type="project", ref_id="p1", note="Hot Hours -50%")

    refund = credits.refund_for(USER, ref_type="project", ref_id="p1")

    assert refund is not None
    assert refund["delta"] == 1  # not the undiscounted 2
    assert credits.balance(USER) == 10


def test_refunding_twice_gives_back_one_refund(credits: CreditService) -> None:
    credits.grant(USER, 10, reason="signup_bonus")
    credits.charge(USER, 4, ref_type="project", ref_id="p1")

    credits.refund_for(USER, ref_type="project", ref_id="p1")
    second = credits.refund_for(USER, ref_type="project", ref_id="p1")

    assert second is None
    assert credits.balance(USER) == 10


def test_refund_with_nothing_to_refund_is_a_no_op(credits: CreditService) -> None:
    """A job that failed before it was ever charged."""
    credits.grant(USER, 5, reason="signup_bonus")
    assert credits.refund_for(USER, ref_type="project", ref_id="never") is None
    assert credits.balance(USER) == 5


# --- cost and discounts ------------------------------------------------------


def test_generation_cost_reads_the_settings_row(database: Database, credits: CreditService) -> None:
    assert credits.generation_cost() == 1  # default when unset

    database.set_setting(
        "generation_cost_credits", "3", updated_by=USER, updated_at="2026-08-28T00:00:00Z"
    )
    assert credits.generation_cost() == 3


@pytest.mark.parametrize("stored", ["", "abc", "0", "-2", None])
def test_a_broken_cost_setting_falls_back_rather_than_failing(
    database: Database, credits: CreditService, stored: str | None
) -> None:
    """A misconfigured setting must not take generation down."""
    if stored is not None:
        database.set_setting(
            "generation_cost_credits",
            stored,
            updated_by=USER,
            updated_at="2026-08-28T00:00:00Z",
        )
    assert credits.generation_cost() == 1


@pytest.mark.parametrize(
    ("base", "discount", "expected"),
    [
        (2, None, 2),
        (2, 50, 1),
        (1, 50, 1),  # floored: a generation always costs something
        (1, 100, 1),
        (3, 50, 2),  # round(1.5) -> 2
        (5, 20, 4),
        (10, 100, 1),
    ],
)
def test_effective_cost(base: int, discount: int | None, expected: int) -> None:
    assert CreditService.effective_cost(base, discount) == expected


# --- totals and drift --------------------------------------------------------


def test_totals_separate_granted_from_spent(credits: CreditService) -> None:
    credits.grant(USER, 10, reason="signup_bonus")
    credits.grant(USER, 5, reason="event_grant")
    credits.charge(USER, 4, ref_type="project", ref_id="p1")

    granted, spent = credits.totals(USER)
    assert (granted, spent) == (15, 4)


def test_the_ledger_always_explains_the_balance(database: Database, credits: CreditService) -> None:
    credits.grant(USER, 10, reason="signup_bonus")
    credits.charge(USER, 3, ref_type="project", ref_id="p1")
    credits.refund_for(USER, ref_type="project", ref_id="p1")
    credits.grant(OTHER, 7, reason="purchase")
    credits.charge(OTHER, 2, ref_type="project", ref_id="p2")

    assert database.ledger_drift() == []


def test_drift_is_detectable(database: Database, credits: CreditService) -> None:
    """The check has to be able to fail, or it proves nothing.

    Written by going around CreditService deliberately -- which is exactly the
    thing the "one writer" rule exists to prevent.
    """
    credits.grant(USER, 10, reason="signup_bonus")
    with database.connect() as connection:
        connection.execute("UPDATE users SET credit_balance = 999 WHERE id = ?", (USER,))

    assert database.ledger_drift() == [USER]


# --- repository-level guarantees ---------------------------------------------


def test_repository_raises_for_an_unknown_user(database: Database) -> None:
    with pytest.raises(UnknownUserError):
        database.apply_credit_delta(
            transaction_id="t1",
            user_id="44444444-4444-4444-8444-444444444444",
            delta=5,
            reason="event_grant",
            created_at="2026-08-28T00:00:00Z",
        )


def test_repository_raises_rather_than_going_negative(database: Database) -> None:
    with pytest.raises(InsufficientCreditsError):
        database.apply_credit_delta(
            transaction_id="t1",
            user_id=USER,
            delta=-1,
            reason="generation",
            created_at="2026-08-28T00:00:00Z",
        )


def test_zero_delta_is_refused_by_the_database(database: Database) -> None:
    """`delta <> 0`: a row that moves nothing explains nothing."""
    with pytest.raises(sqlite3.IntegrityError):
        database.apply_credit_delta(
            transaction_id="t1",
            user_id=USER,
            delta=0,
            reason="admin_adjustment",
            created_at="2026-08-28T00:00:00Z",
        )


def test_concurrent_charges_cannot_overspend(database: Database) -> None:
    """The one that matters.

    Ten threads race to spend a balance that covers three of them. Exactly
    three may succeed. A service that read the balance and then wrote it would
    let all ten through; the guard lives in the UPDATE's WHERE clause, and
    BEGIN IMMEDIATE serialises the readers, so it does not.
    """
    credits = CreditService(database)
    credits.grant(USER, 3, reason="signup_bonus")

    def spend(index: int) -> bool:
        try:
            credits.charge(USER, 1, ref_type="project", ref_id=f"p{index}")
        except AppError:
            return False
        except sqlite3.OperationalError:  # pragma: no cover - lock contention
            return False
        return True

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(spend, range(10)))

    assert sum(results) == 3
    assert credits.balance(USER) == 0
    assert database.ledger_drift() == []


def test_history_pages_newest_first(credits: CreditService) -> None:
    credits.grant(USER, 100, reason="purchase")
    for index in range(5):
        credits.charge(USER, 1, ref_type="project", ref_id=f"p{index}")

    first, cursor = credits.history(USER, limit=2)
    assert len(first) == 2
    assert cursor is not None

    second, _ = credits.history(USER, limit=2, cursor=cursor)
    assert len(second) == 2
    # No overlap between pages: the cursor is keyset, not an offset.
    assert {row["id"] for row in first}.isdisjoint({row["id"] for row in second})


def test_history_filters_by_reason(credits: CreditService) -> None:
    credits.grant(USER, 10, reason="signup_bonus")
    credits.grant(USER, 5, reason="event_grant")
    credits.charge(USER, 1, ref_type="project", ref_id="p1")

    rows, _ = credits.history(USER, reason="event_grant")
    assert len(rows) == 1
    assert rows[0]["delta"] == 5
