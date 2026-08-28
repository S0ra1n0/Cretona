"""The credit, package and payment endpoints (S-07).

Contract: docs/API_CONTRACT.md Part II §6, §8, §9.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.conftest import USER_A

HEADERS = {"X-Debug-User-Id": USER_A}
REPO = Path(__file__).resolve().parents[2]


def key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4()), **HEADERS}


def provision(client: TestClient, credits: int = 0) -> None:
    client.app.state.database.upsert_user(USER_A, email="a@example.com", username="a")
    if credits:
        client.app.state.credit_service.grant(USER_A, credits, reason="purchase")


def balance(client: TestClient) -> int:
    return client.app.state.credit_service.balance(USER_A)


# --- GET /me/credits ---------------------------------------------------------


def test_balance_reports_cost_and_lifetime_totals(client: TestClient) -> None:
    provision(client, 10)

    body = client.get("/api/v1/me/credits", headers=HEADERS).json()

    assert body["balance"] == 10
    assert body["generationCost"] == 1
    assert body["effectiveCost"] == 1
    assert body["activeDiscount"] is None
    assert body["lifetimeGranted"] == 10
    assert body["lifetimeSpent"] == 0


def test_spending_moves_the_lifetime_totals(client: TestClient) -> None:
    provision(client, 10)
    client.post("/api/v1/projects", headers=HEADERS, json={"prompt": "a dragon"})

    body = client.get("/api/v1/me/credits", headers=HEADERS).json()

    assert body["balance"] == 9
    assert body["lifetimeGranted"] == 10
    assert body["lifetimeSpent"] == 1


# --- GET /me/credits/transactions --------------------------------------------


def test_the_ledger_is_returned_newest_first(client: TestClient) -> None:
    provision(client, 10)
    client.post("/api/v1/projects", headers=HEADERS, json={"prompt": "one"})

    items = client.get("/api/v1/me/credits/transactions", headers=HEADERS).json()["items"]

    assert [row["reason"] for row in items] == ["generation", "purchase"]
    assert items[0]["delta"] == -1
    assert items[0]["refType"] == "project"
    assert items[0]["createdAt"].endswith("Z")


def test_the_ledger_pages_without_overlap(client: TestClient) -> None:
    provision(client, 20)
    for index in range(4):
        client.app.state.credit_service.grant(
            USER_A, 1, reason="event_grant", note=f"grant {index}"
        )

    first = client.get("/api/v1/me/credits/transactions?limit=2", headers=HEADERS).json()
    assert len(first["items"]) == 2
    assert first["nextCursor"]

    second = client.get(
        f"/api/v1/me/credits/transactions?limit=2&cursor={first['nextCursor']}",
        headers=HEADERS,
    ).json()

    ids = {row["id"] for row in first["items"]}
    assert ids.isdisjoint({row["id"] for row in second["items"]})


def test_the_ledger_is_the_callers_own(client: TestClient) -> None:
    provision(client, 5)
    other = "20000000-0000-4000-8000-000000000002"
    client.app.state.database.upsert_user(other, email="b@example.com")
    client.app.state.credit_service.grant(other, 99, reason="admin_adjustment")

    items = client.get("/api/v1/me/credits/transactions", headers=HEADERS).json()["items"]

    assert all(row["delta"] != 99 for row in items)


# --- GET /credit-packages ----------------------------------------------------


def test_packages_are_listed_in_order(client: TestClient) -> None:
    provision(client)

    items = client.get("/api/v1/credit-packages", headers=HEADERS).json()["items"]

    assert [row["name"] for row in items] == ["Starter", "Creator", "Studio"]
    assert items[0]["credits"] == 10
    assert items[0]["priceVnd"] == 20000


def test_inactive_packages_are_hidden(client: TestClient) -> None:
    provision(client)
    with client.app.state.database.connect() as connection:
        connection.execute("UPDATE credit_packages SET is_active = 0 WHERE name = 'Studio'")

    names = [
        row["name"]
        for row in client.get("/api/v1/credit-packages", headers=HEADERS).json()["items"]
    ]

    assert "Studio" not in names


def test_sqlite_defaults_match_the_seed(client: TestClient) -> None:
    """The sqlite mirror duplicates the Supabase seed. Catch it drifting.

    `Database._seed_defaults` exists so a local demo has packages to buy, but
    prices living in two places is exactly how they end up disagreeing.
    """
    sql = (REPO / "supabase/seed_credits_and_events.sql").read_text(encoding="utf-8")
    from_sql = {
        (name, int(credits), int(price))
        for name, credits, price in re.findall(
            r"\('(Starter|Creator|Studio)',\s*(\d+),\s*(\d+),\s*\d+\)", sql
        )
    }
    from_sqlite = {
        (row["name"], row["credits"], row["priceVnd"])
        for row in client.get("/api/v1/credit-packages", headers=HEADERS).json()["items"]
    }

    assert from_sql, "could not parse packages out of the seed file"
    assert from_sqlite == from_sql


# --- POST /payments ----------------------------------------------------------


def test_a_purchase_grants_credits_and_returns_the_new_balance(
    client: TestClient,
) -> None:
    provision(client)
    package = client.get("/api/v1/credit-packages", headers=HEADERS).json()["items"][0]

    response = client.post("/api/v1/payments", headers=key(), json={"packageId": package["id"]})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["creditsGranted"] == 10
    assert body["balance"] == 10
    # ADR-010: the row itself discloses the simulation.
    assert body["method"] == "simulated"
    assert body["completedAt"]
    assert balance(client) == 10


def test_a_purchase_writes_one_ledger_row(client: TestClient) -> None:
    provision(client)
    package = client.get("/api/v1/credit-packages", headers=HEADERS).json()["items"][0]
    payment = client.post(
        "/api/v1/payments", headers=key(), json={"packageId": package["id"]}
    ).json()

    items = client.get("/api/v1/me/credits/transactions", headers=HEADERS).json()["items"]

    assert len(items) == 1
    assert items[0]["reason"] == "purchase"
    assert items[0]["delta"] == 10
    assert items[0]["refType"] == "payment"
    assert items[0]["refId"] == payment["id"]


def test_a_replayed_purchase_grants_once(client: TestClient) -> None:
    """The reason the key is mandatory: a retry must not double the credits."""
    provision(client)
    package = client.get("/api/v1/credit-packages", headers=HEADERS).json()["items"][0]
    headers = key()

    first = client.post("/api/v1/payments", headers=headers, json={"packageId": package["id"]})
    second = client.post("/api/v1/payments", headers=headers, json={"packageId": package["id"]})

    assert first.json()["id"] == second.json()["id"]
    assert balance(client) == 10
    items = client.get("/api/v1/me/credits/transactions", headers=HEADERS).json()["items"]
    assert len(items) == 1


def test_a_purchase_without_an_idempotency_key_is_refused(client: TestClient) -> None:
    provision(client)
    package = client.get("/api/v1/credit-packages", headers=HEADERS).json()["items"][0]

    response = client.post("/api/v1/payments", headers=HEADERS, json={"packageId": package["id"]})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert balance(client) == 0


def test_a_malformed_idempotency_key_is_refused(client: TestClient) -> None:
    provision(client)
    package = client.get("/api/v1/credit-packages", headers=HEADERS).json()["items"][0]

    response = client.post(
        "/api/v1/payments",
        headers={"Idempotency-Key": "not-a-uuid", **HEADERS},
        json={"packageId": package["id"]},
    )

    assert response.status_code == 400
    assert balance(client) == 0


def test_an_unknown_package_is_not_found(client: TestClient) -> None:
    provision(client)

    response = client.post(
        "/api/v1/payments",
        headers=key(),
        json={"packageId": "00000000-0000-4000-8000-0000000000ff"},
    )

    assert response.status_code == 404
    assert balance(client) == 0


def test_a_withdrawn_package_is_refused_with_its_own_code(client: TestClient) -> None:
    """Listed a moment ago, deactivated since. The app refreshes, not retries."""
    provision(client)
    package = client.get("/api/v1/credit-packages", headers=HEADERS).json()["items"][0]
    with client.app.state.database.connect() as connection:
        connection.execute(
            "UPDATE credit_packages SET is_active = 0 WHERE id = ?", (package["id"],)
        )

    response = client.post("/api/v1/payments", headers=key(), json={"packageId": package["id"]})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PACKAGE_INACTIVE"
    assert balance(client) == 0


def test_a_refused_purchase_leaves_no_payment_row(client: TestClient) -> None:
    provision(client)
    client.post(
        "/api/v1/payments",
        headers=key(),
        json={"packageId": "00000000-0000-4000-8000-0000000000ff"},
    )

    with client.app.state.database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) AS n FROM payments").fetchone()["n"]

    assert count == 0
    assert client.app.state.database.ledger_drift() == []


def test_buying_makes_a_broke_account_able_to_generate(client: TestClient) -> None:
    """The whole point of the flow, end to end."""
    provision(client)
    assert client.post("/api/v1/projects", headers=HEADERS, json={"prompt": "x"}).status_code == 402

    package = client.get("/api/v1/credit-packages", headers=HEADERS).json()["items"][0]
    client.post("/api/v1/payments", headers=key(), json={"packageId": package["id"]})

    assert client.post("/api/v1/projects", headers=HEADERS, json={"prompt": "x"}).status_code == 201


# --- GET /admin/credits/drift ------------------------------------------------


def test_drift_reports_healthy_after_a_full_cycle(client: TestClient) -> None:
    admin = "30000000-0000-4000-8000-000000000003"
    client.app.state.database.upsert_user(admin, email="admin@example.com", role="admin")
    provision(client, 10)
    project = client.post("/api/v1/projects", headers=HEADERS, json={"prompt": "one"}).json()
    client.post(f"/api/v1/projects/{project['id']}/cancel", headers=HEADERS)

    body = client.get("/api/v1/admin/credits/drift", headers={"X-Debug-User-Id": admin}).json()

    assert body["healthy"] is True
    assert body["driftedUserIds"] == []
    assert body["checkedAt"].endswith("Z")


def test_drift_reports_an_account_written_behind_the_service(client: TestClient) -> None:
    """It has to be able to fail, or it is not a check.

    A silently failed refund would show up exactly like this, and nothing else
    would show it at all.
    """
    admin = "30000000-0000-4000-8000-000000000003"
    client.app.state.database.upsert_user(admin, email="admin@example.com", role="admin")
    provision(client, 10)
    with client.app.state.database.connect() as connection:
        connection.execute("UPDATE users SET credit_balance = 4321 WHERE id = ?", (USER_A,))

    body = client.get("/api/v1/admin/credits/drift", headers={"X-Debug-User-Id": admin}).json()

    assert body["healthy"] is False
    assert body["driftedUserIds"] == [USER_A]


def test_drift_is_admin_only(client: TestClient) -> None:
    provision(client, 5)

    response = client.get("/api/v1/admin/credits/drift", headers=HEADERS)

    assert response.status_code == 403
