"""The extended admin dashboard figures (S-15).

Brief §3 asks for six report metrics. Four were missing: new users, credits
granted, credits used, and revenue from credit sales — plus per-campaign
take-up. This covers those.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import USER_A

ADMIN = "30000000-0000-4000-8000-000000000003"
ADMIN_HEADERS = {"X-Debug-User-Id": ADMIN}
USER_HEADERS = {"X-Debug-User-Id": USER_A}
OTHER = "20000000-0000-4000-8000-000000000002"


def setup(client: TestClient) -> None:
    database = client.app.state.database
    database.upsert_user(ADMIN, email="admin@example.com", username="admin", role="admin")
    database.upsert_user(USER_A, email="a@example.com", username="a")


def stats(client: TestClient) -> dict:
    return client.get("/api/v1/admin/stats", headers=ADMIN_HEADERS).json()


# --- totals ------------------------------------------------------------------


def test_an_empty_system_reports_zeroes_not_nulls(client: TestClient) -> None:
    """A dashboard tile bound to null renders blank, which reads as broken."""
    setup(client)

    totals = stats(client)["totals"]

    assert totals["creditsGranted"] == 0
    assert totals["creditsUsed"] == 0
    assert totals["revenueVnd"] == 0


def test_credits_granted_and_used_are_separate_figures(client: TestClient) -> None:
    setup(client)
    client.app.state.credit_service.grant(USER_A, 30, reason="purchase")
    client.post("/api/v1/projects", headers=USER_HEADERS, json={"prompt": "a dragon"})

    totals = stats(client)["totals"]

    assert totals["creditsGranted"] == 30
    assert totals["creditsUsed"] == 1


def test_a_refund_counts_as_a_grant_not_as_negative_spend(client: TestClient) -> None:
    """The ledger is signed; these two figures are its two halves.

    A refund is a positive delta, so it lands in `creditsGranted`. Netting it
    off `creditsUsed` instead would make "credits used" mean something no
    single query produces, and the two would stop summing to the balance.
    """
    setup(client)
    client.app.state.credit_service.grant(USER_A, 10, reason="purchase")
    project = client.post("/api/v1/projects", headers=USER_HEADERS, json={"prompt": "one"}).json()
    client.post(f"/api/v1/projects/{project['id']}/cancel", headers=USER_HEADERS)

    totals = stats(client)["totals"]

    assert totals["creditsGranted"] == 11  # 10 purchased + 1 refunded
    assert totals["creditsUsed"] == 1


def test_revenue_counts_completed_payments(client: TestClient) -> None:
    setup(client)
    package = client.get("/api/v1/credit-packages", headers=USER_HEADERS).json()["items"][0]
    client.post(
        "/api/v1/payments",
        headers={"Idempotency-Key": "11111111-1111-4111-8111-aaaaaaaaaaaa", **USER_HEADERS},
        json={"packageId": package["id"]},
    )

    assert stats(client)["totals"]["revenueVnd"] == package["priceVnd"]


def test_revenue_ignores_payments_that_did_not_complete(client: TestClient) -> None:
    setup(client)
    with client.app.state.database.connect() as connection:
        connection.execute(
            "INSERT INTO payments (id, user_id, package_id, amount_vnd, credits_granted, "
            " method, status, created_at) "
            "VALUES ('p1', ?, 'pkg', 999999, 10, 'simulated', 'failed', ?)",
            (USER_A, "2026-08-28T00:00:00Z"),
        )

    assert stats(client)["totals"]["revenueVnd"] == 0


# --- the daily series --------------------------------------------------------


def test_new_users_counts_signups_not_projects(client: TestClient) -> None:
    """`created` counts generations. They are different numbers."""
    setup(client)
    client.app.state.database.upsert_user(
        OTHER, email="b@example.com", created_at="2026-08-28T10:00:00Z"
    )
    client.app.state.credit_service.grant(USER_A, 10, reason="purchase")
    client.post("/api/v1/projects", headers=USER_HEADERS, json={"prompt": "one"})
    client.post("/api/v1/projects", headers=USER_HEADERS, json={"prompt": "two"})

    daily = stats(client)["daily"]

    created = sum(row["created"] for row in daily)
    new_users = sum(row["newUsers"] for row in daily)
    assert created == 2
    assert new_users != created


def test_a_day_with_credits_but_no_projects_still_appears(client: TestClient) -> None:
    """Four separate queries, merged by date.

    Joined into one, a day where credits moved but nothing was generated would
    vanish — and a revenue chart with holes looks like data rather than a bug.
    """
    setup(client)
    client.app.state.credit_service.grant(USER_A, 40, reason="event_grant")

    daily = stats(client)["daily"]

    assert daily, "a credit grant alone should produce a day"
    assert sum(row["creditsGranted"] for row in daily) == 40
    assert sum(row["created"] for row in daily) == 0


def test_the_daily_series_carries_all_four_new_figures(client: TestClient) -> None:
    setup(client)
    package = client.get("/api/v1/credit-packages", headers=USER_HEADERS).json()["items"][0]
    client.post(
        "/api/v1/payments",
        headers={"Idempotency-Key": "22222222-2222-4222-8222-bbbbbbbbbbbb", **USER_HEADERS},
        json={"packageId": package["id"]},
    )
    client.post("/api/v1/projects", headers=USER_HEADERS, json={"prompt": "one"})

    today = stats(client)["daily"][0]

    for key in ("newUsers", "creditsGranted", "creditsUsed", "revenueVnd"):
        assert key in today, key
    assert today["creditsUsed"] == 1
    assert today["revenueVnd"] == package["priceVnd"]


def test_days_come_back_newest_first(client: TestClient) -> None:
    setup(client)
    client.app.state.credit_service.grant(USER_A, 5, reason="purchase")

    dates = [row["date"] for row in stats(client)["daily"]]

    assert dates == sorted(dates, reverse=True)


# --- per-campaign take-up ----------------------------------------------------


def test_every_event_appears_even_with_no_claims(client: TestClient) -> None:
    """An event nobody took up is exactly what an admin needs to see."""
    setup(client)

    codes = {row["code"] for row in stats(client)["events"]}

    assert "SIGNUP_BONUS" in codes
    signup = next(row for row in stats(client)["events"] if row["code"] == "SIGNUP_BONUS")
    assert signup["claims"] == 0


def test_claims_and_credits_are_counted_per_event(client: TestClient) -> None:
    setup(client)
    created = client.post(
        "/api/v1/admin/events",
        headers=ADMIN_HEADERS,
        json={
            "code": "TAKEUP",
            "name": "Take-up",
            "kind": "grant",
            "bonusCredits": 12,
            "recurrence": "once",
            "startsAt": "2026-08-01T00:00:00Z",
            "endsAt": "2027-01-01T00:00:00Z",
            "maxClaims": 5,
        },
    ).json()
    client.post(f"/api/v1/events/{created['id']}/claim", headers=USER_HEADERS)

    row = next(item for item in stats(client)["events"] if item["code"] == "TAKEUP")

    assert row["claims"] == 1
    assert row["creditsGranted"] == 12
    assert row["remainingSlots"] == 4


def test_an_uncapped_event_reports_no_remaining_slots(client: TestClient) -> None:
    """None, not a number — "unlimited" and "zero left" must not look alike."""
    setup(client)

    signup = next(row for row in stats(client)["events"] if row["code"] == "SIGNUP_BONUS")

    assert signup["remainingSlots"] is None


# --- the existing figures are unchanged --------------------------------------


def test_the_original_fields_still_work(client: TestClient) -> None:
    setup(client)
    client.app.state.credit_service.grant(USER_A, 10, reason="purchase")
    client.post("/api/v1/projects", headers=USER_HEADERS, json={"prompt": "one"})

    body = stats(client)

    assert body["totals"]["users"] >= 2
    assert body["projectsByStatus"]["pending"] == 1
    assert "fake" in body["projectsByProvider"] or body["projectsByProvider"]
    assert body["failureRate"] == 0.0


def test_stats_stay_admin_only(client: TestClient) -> None:
    setup(client)

    assert client.get("/api/v1/admin/stats", headers=USER_HEADERS).status_code == 403
