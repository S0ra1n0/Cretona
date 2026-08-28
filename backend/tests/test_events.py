"""Event windows, claiming and the discount at charge time (S-11).

The window logic is where this is easiest to get wrong, and the failure is
silent: an event that never opens looks the same as one nobody wanted, and one
that never closes gives away credits forever. Every case is pinned to a fixed
instant rather than `now`, so these do not pass or fail depending on when the
suite runs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.event_service import LOCAL, EventService
from tests.conftest import USER_A

HEADERS = {"X-Debug-User-Id": USER_A}


def at(text: str) -> datetime:
    """A moment in local Vietnam time, which is how campaigns are written."""
    return datetime.fromisoformat(text).replace(tzinfo=LOCAL)


def event(**overrides) -> dict:
    base = {
        "id": str(uuid4()),
        "code": "TEST",
        "name": "Test event",
        "kind": "grant",
        "bonus_credits": 10,
        "discount_percent": None,
        "recurrence": "once",
        "active_days": None,
        "active_from_minute": None,
        "active_to_minute": None,
        "starts_at": "2026-08-01T00:00:00Z",
        "ends_at": "2027-01-01T00:00:00Z",
        "max_claims": None,
        "auto_grant": False,
        "is_active": True,
    }
    base.update(overrides)
    return base


# --- the campaign window -----------------------------------------------------


def test_an_event_outside_its_campaign_is_closed() -> None:
    campaign = event(starts_at="2026-09-01T00:00:00Z", ends_at="2026-09-03T00:00:00Z")

    assert EventService.is_active(campaign, at("2026-08-31T12:00")) is False
    assert EventService.is_active(campaign, at("2026-09-02T12:00")) is True
    assert EventService.is_active(campaign, at("2026-09-04T12:00")) is False


def test_a_deactivated_event_is_closed_even_inside_its_window() -> None:
    assert EventService.is_active(event(is_active=False), at("2026-08-28T12:00")) is False


# --- hot hours: a daily minute window ----------------------------------------


@pytest.mark.parametrize(
    ("local_time", "open_"),
    [
        ("2026-08-28T19:59", False),
        ("2026-08-28T20:00", True),  # inclusive start
        ("2026-08-28T21:30", True),
        ("2026-08-28T21:59", True),
        ("2026-08-28T22:00", False),  # exclusive end
        ("2026-08-29T20:30", True),  # and again the next day
    ],
)
def test_hot_hours_opens_between_2000_and_2200_local(local_time: str, open_: bool) -> None:
    hot = event(
        kind="discount",
        bonus_credits=None,
        discount_percent=50,
        recurrence="daily",
        active_from_minute=1200,
        active_to_minute=1320,
    )

    assert EventService.is_active(hot, at(local_time)) is open_


def test_hot_hours_is_judged_in_vietnam_time_not_utc() -> None:
    """20:00 local is 13:00 UTC. Judging in UTC would open it at the wrong time.

    This is the bug the whole LOCAL constant exists to prevent, and it would
    have looked like "the discount is broken for some users".
    """
    hot = event(
        kind="discount",
        bonus_credits=None,
        discount_percent=50,
        recurrence="daily",
        active_from_minute=1200,
        active_to_minute=1320,
    )

    assert EventService.is_active(hot, datetime(2026, 8, 28, 13, 30, tzinfo=UTC)) is True
    assert EventService.is_active(hot, datetime(2026, 8, 28, 20, 30, tzinfo=UTC)) is False


def test_a_window_that_wraps_midnight_is_two_ranges() -> None:
    """22:00 to 02:00. Treated as one range it would never be open at all."""
    late = event(recurrence="daily", active_from_minute=1320, active_to_minute=120)

    assert EventService.is_active(late, at("2026-08-28T23:00")) is True
    assert EventService.is_active(late, at("2026-08-29T01:00")) is True
    assert EventService.is_active(late, at("2026-08-29T03:00")) is False
    assert EventService.is_active(late, at("2026-08-29T12:00")) is False


# --- weekend gift: a weekly day filter ---------------------------------------


@pytest.mark.parametrize(
    ("local_date", "open_"),
    [
        ("2026-08-28T12:00", False),  # Friday
        ("2026-08-29T12:00", True),  # Saturday
        ("2026-08-30T12:00", True),  # Sunday
        ("2026-08-31T12:00", False),  # Monday
    ],
)
def test_the_weekend_gift_only_opens_at_the_weekend(local_date: str, open_: bool) -> None:
    weekend = event(recurrence="weekly", active_days="sat,sun")

    assert EventService.is_active(weekend, at(local_date)) is open_


# --- period keys: what "once per occurrence" means ---------------------------


def test_a_once_event_has_a_single_period() -> None:
    once = event(recurrence="once")

    assert EventService.period_key(once, at("2026-08-28T12:00")) == ""
    assert EventService.period_key(once, at("2026-12-25T12:00")) == ""


def test_a_daily_event_gets_a_new_period_each_local_day() -> None:
    daily = event(recurrence="daily")

    assert EventService.period_key(daily, at("2026-08-28T23:30")) == "2026-08-28"
    assert EventService.period_key(daily, at("2026-08-29T00:30")) == "2026-08-29"


def test_a_weekly_event_gets_a_new_period_each_iso_week() -> None:
    weekly = event(recurrence="weekly")

    saturday = EventService.period_key(weekly, at("2026-08-29T12:00"))
    sunday = EventService.period_key(weekly, at("2026-08-30T12:00"))
    next_saturday = EventService.period_key(weekly, at("2026-09-05T12:00"))

    # Sat and Sun are the same weekend, so one claim covers both.
    assert saturday == sunday
    assert next_saturday != saturday


# --- claiming, through the API -----------------------------------------------


def provision(client: TestClient) -> None:
    client.app.state.database.upsert_user(USER_A, email="a@example.com", username="a")


def insert_event(client: TestClient, **overrides) -> str:
    row = event(**overrides)
    with client.app.state.database.connect() as connection:
        connection.execute(
            "INSERT INTO events (id, code, name, kind, bonus_credits, discount_percent, "
            " recurrence, active_days, active_from_minute, active_to_minute, starts_at, "
            " ends_at, max_claims, auto_grant, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["id"],
                row["code"] + row["id"][:8],
                row["name"],
                row["kind"],
                row["bonus_credits"],
                row["discount_percent"],
                row["recurrence"],
                row["active_days"],
                row["active_from_minute"],
                row["active_to_minute"],
                row["starts_at"],
                row["ends_at"],
                row["max_claims"],
                int(row["auto_grant"]),
                int(row["is_active"]),
                "2026-08-01T00:00:00Z",
            ),
        )
    return row["id"]


def balance(client: TestClient) -> int:
    return client.app.state.credit_service.balance(USER_A)


def test_claiming_grants_the_credits(client: TestClient) -> None:
    provision(client)
    event_id = insert_event(client, bonus_credits=15)
    before = balance(client)

    body = client.post(f"/api/v1/events/{event_id}/claim", headers=HEADERS).json()

    assert body["creditsGranted"] == 15
    assert body["balance"] == before + 15
    assert balance(client) == before + 15


def test_claiming_writes_one_ledger_row(client: TestClient) -> None:
    provision(client)
    event_id = insert_event(client, bonus_credits=15)
    client.post(f"/api/v1/events/{event_id}/claim", headers=HEADERS)

    items = client.get("/api/v1/me/credits/transactions", headers=HEADERS).json()["items"]

    grant = next(row for row in items if row["reason"] == "event_grant")
    assert grant["delta"] == 15
    assert grant["refType"] == "event"
    assert grant["refId"] == event_id


def test_claiming_twice_in_the_same_period_is_refused(client: TestClient) -> None:
    provision(client)
    event_id = insert_event(client, bonus_credits=10)
    client.post(f"/api/v1/events/{event_id}/claim", headers=HEADERS)
    before = balance(client)

    response = client.post(f"/api/v1/events/{event_id}/claim", headers=HEADERS)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVENT_ALREADY_CLAIMED"
    assert balance(client) == before


def test_a_full_event_is_refused_with_its_own_code(client: TestClient) -> None:
    provision(client)
    event_id = insert_event(client, bonus_credits=10, max_claims=1)
    other = "20000000-0000-4000-8000-000000000002"
    client.app.state.database.upsert_user(other, email="b@example.com")
    # Someone else takes the only slot.
    client.app.state.event_service.claim(other, event_id)
    before = balance(client)

    response = client.post(f"/api/v1/events/{event_id}/claim", headers=HEADERS)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVENT_FULL"
    assert balance(client) == before


def test_a_discount_cannot_be_claimed(client: TestClient) -> None:
    """It applies by itself; a button here would always fail."""
    provision(client)
    event_id = insert_event(client, kind="discount", bonus_credits=None, discount_percent=50)

    response = client.post(f"/api/v1/events/{event_id}/claim", headers=HEADERS)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVENT_NOT_ACTIVE"


def test_a_closed_event_cannot_be_claimed(client: TestClient) -> None:
    provision(client)
    event_id = insert_event(
        client, starts_at="2020-01-01T00:00:00Z", ends_at="2020-02-01T00:00:00Z"
    )

    response = client.post(f"/api/v1/events/{event_id}/claim", headers=HEADERS)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVENT_NOT_ACTIVE"


def test_the_cap_holds_under_concurrent_claims(client: TestClient) -> None:
    """A double-tap must not take two of three slots.

    The guard is the INSERT's WHERE clause, not a count followed by a write.
    """
    from concurrent.futures import ThreadPoolExecutor

    event_id = insert_event(client, bonus_credits=1, max_claims=3)
    users = [f"4000000{index}-0000-4000-8000-000000000001" for index in range(8)]
    for user in users:
        client.app.state.database.upsert_user(user, email=f"{user[:8]}@example.com")

    service = client.app.state.event_service

    def take(user: str) -> bool:
        try:
            service.claim(user, event_id)
        except Exception:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(take, users))

    assert sum(results) == 3
    assert client.app.state.database.count_event_claims(event_id) == 3
    assert client.app.state.database.ledger_drift() == []


# --- the listing -------------------------------------------------------------


def test_the_seeded_events_are_listed(client: TestClient) -> None:
    provision(client)

    items = client.get("/api/v1/events", headers=HEADERS).json()["items"]

    assert any(row["code"] == "SIGNUP_BONUS" for row in items)


def test_an_auto_grant_event_is_never_claimable(client: TestClient) -> None:
    """The signup bonus applies on its own. Offering a button would confuse."""
    provision(client)

    items = client.get("/api/v1/events", headers=HEADERS).json()["items"]

    signup = next(row for row in items if row["code"] == "SIGNUP_BONUS")
    assert signup["claimable"] is False


def test_the_listing_reports_remaining_slots(client: TestClient) -> None:
    provision(client)
    event_id = insert_event(client, bonus_credits=5, max_claims=4)
    client.post(f"/api/v1/events/{event_id}/claim", headers=HEADERS)

    items = client.get("/api/v1/events", headers=HEADERS).json()["items"]

    row = next(item for item in items if item["id"] == event_id)
    assert row["remainingSlots"] == 3
    assert row["claimedThisPeriod"] is True
    assert row["claimable"] is False


def test_an_uncapped_event_reports_no_slot_count(client: TestClient) -> None:
    provision(client)
    event_id = insert_event(client, bonus_credits=5, max_claims=None)

    items = client.get("/api/v1/events", headers=HEADERS).json()["items"]

    row = next(item for item in items if item["id"] == event_id)
    assert row["remainingSlots"] is None
    assert row["claimable"] is True


# --- the discount reaching the price -----------------------------------------


def test_a_discount_lowers_what_a_generation_costs(client: TestClient) -> None:
    """The whole point of S-11: Hot Hours has to reach the charge."""
    provision(client)
    client.app.state.credit_service.grant(USER_A, 10, reason="purchase")
    with client.app.state.database.connect() as connection:
        connection.execute(
            "UPDATE settings SET value = '2' WHERE key = ?", ("generation_cost_credits",)
        )
    # A discount that is open all day, so the test does not depend on the clock.
    insert_event(
        client,
        kind="discount",
        bonus_credits=None,
        discount_percent=50,
        recurrence="once",
    )

    client.post("/api/v1/projects", headers=HEADERS, json={"prompt": "a dragon"})

    assert balance(client) == 9  # 2 credits, halved to 1
    charge = client.get("/api/v1/me/credits/transactions", headers=HEADERS).json()["items"][0]
    assert charge["delta"] == -1
    # The ledger has to say why this row is 1 when yesterday's was 2.
    assert "50%" in (charge["note"] or "")


def test_the_balance_endpoint_reports_the_live_discount(client: TestClient) -> None:
    provision(client)
    with client.app.state.database.connect() as connection:
        connection.execute(
            "UPDATE settings SET value = '2' WHERE key = ?", ("generation_cost_credits",)
        )
    insert_event(
        client,
        kind="discount",
        bonus_credits=None,
        discount_percent=50,
        recurrence="once",
        name="Hot Hours",
    )

    body = client.get("/api/v1/me/credits", headers=HEADERS).json()

    assert body["generationCost"] == 2
    assert body["effectiveCost"] == 1
    assert body["activeDiscount"]["discountPercent"] == 50
    assert body["activeDiscount"]["name"] == "Hot Hours"


def test_no_discount_means_the_full_price(client: TestClient) -> None:
    provision(client)

    body = client.get("/api/v1/me/credits", headers=HEADERS).json()

    assert body["activeDiscount"] is None
    assert body["effectiveCost"] == body["generationCost"]


def test_a_refund_returns_the_discounted_amount_not_the_full_price(
    client: TestClient,
) -> None:
    """Contract §10.4, now that a discount can actually make them differ."""
    provision(client)
    client.app.state.credit_service.grant(USER_A, 10, reason="purchase")
    with client.app.state.database.connect() as connection:
        connection.execute(
            "UPDATE settings SET value = '2' WHERE key = ?", ("generation_cost_credits",)
        )
    discount_id = insert_event(
        client,
        kind="discount",
        bonus_credits=None,
        discount_percent=50,
        recurrence="once",
    )
    project = client.post("/api/v1/projects", headers=HEADERS, json={"prompt": "one"}).json()
    assert balance(client) == 9

    # The campaign ends before the job does.
    with client.app.state.database.connect() as connection:
        connection.execute("UPDATE events SET is_active = 0 WHERE id = ?", (discount_id,))

    client.post(f"/api/v1/projects/{project['id']}/cancel", headers=HEADERS)

    # 1 back, not the 2 it would cost now.
    assert balance(client) == 10
    assert client.app.state.database.ledger_drift() == []
