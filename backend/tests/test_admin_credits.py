"""Admin control over credits, packages, events and the generation cost (S-16).

Brief §3: an admin adds and subtracts credits, configures what a generation
costs, manages packages, and creates promotions with a window, a grant and a
registration cap.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import USER_A

ADMIN = "30000000-0000-4000-8000-000000000003"
ADMIN_HEADERS = {"X-Debug-User-Id": ADMIN}
USER_HEADERS = {"X-Debug-User-Id": USER_A}


def setup(client: TestClient, credits: int = 0) -> None:
    database = client.app.state.database
    database.upsert_user(ADMIN, email="admin@example.com", username="admin", role="admin")
    database.upsert_user(USER_A, email="a@example.com", username="a")
    if credits:
        client.app.state.credit_service.grant(USER_A, credits, reason="purchase")


def balance(client: TestClient) -> int:
    return client.app.state.credit_service.balance(USER_A)


def audit_actions(client: TestClient) -> list[str]:
    rows, _ = client.app.state.database.list_audit_logs(limit=50, cursor=None)
    return [row["action"] for row in rows]


# --- adjusting credits -------------------------------------------------------


def test_an_admin_can_add_credits(client: TestClient) -> None:
    setup(client)

    response = client.post(
        f"/api/v1/admin/users/{USER_A}/credits",
        headers=ADMIN_HEADERS,
        json={"delta": 25, "note": "compensation"},
    )

    assert response.status_code == 200
    assert response.json()["balance"] == 25
    assert balance(client) == 25


def test_an_admin_can_remove_credits(client: TestClient) -> None:
    setup(client, credits=30)

    response = client.post(
        f"/api/v1/admin/users/{USER_A}/credits",
        headers=ADMIN_HEADERS,
        json={"delta": -10},
    )

    assert response.status_code == 200
    assert balance(client) == 20


def test_an_adjustment_cannot_leave_a_negative_balance(client: TestClient) -> None:
    setup(client, credits=5)

    response = client.post(
        f"/api/v1/admin/users/{USER_A}/credits",
        headers=ADMIN_HEADERS,
        json={"delta": -50},
    )

    assert response.status_code in (402, 409)
    assert balance(client) == 5


def test_a_zero_adjustment_is_refused(client: TestClient) -> None:
    setup(client)

    response = client.post(
        f"/api/v1/admin/users/{USER_A}/credits",
        headers=ADMIN_HEADERS,
        json={"delta": 0},
    )

    assert response.status_code == 400


def test_an_adjustment_leaves_an_audit_trail(client: TestClient) -> None:
    """Money moved by an admin with no record of who moved it is the gap
    T2-5 closed for the rest of the admin surface."""
    setup(client)
    client.post(
        f"/api/v1/admin/users/{USER_A}/credits",
        headers=ADMIN_HEADERS,
        json={"delta": 25, "note": "compensation"},
    )

    assert "credits.adjust" in audit_actions(client)


def test_the_adjustment_appears_in_the_users_ledger(client: TestClient) -> None:
    setup(client)
    client.post(
        f"/api/v1/admin/users/{USER_A}/credits",
        headers=ADMIN_HEADERS,
        json={"delta": 25, "note": "compensation"},
    )

    items = client.get(
        "/api/v1/me/credits/transactions", headers=USER_HEADERS
    ).json()["items"]

    assert items[0]["reason"] == "admin_adjustment"
    assert items[0]["note"] == "compensation"


def test_adjusting_credits_is_admin_only(client: TestClient) -> None:
    setup(client)

    response = client.post(
        f"/api/v1/admin/users/{USER_A}/credits",
        headers=USER_HEADERS,
        json={"delta": 999},
    )

    assert response.status_code == 403
    assert balance(client) == 0


# --- the generation cost -----------------------------------------------------


def test_an_admin_can_change_what_a_generation_costs(client: TestClient) -> None:
    """Brief §3: "cấu hình chi phí tạo video"."""
    setup(client, credits=20)
    assert client.get("/api/v1/admin/settings", headers=ADMIN_HEADERS).json()[
        "generationCostCredits"
    ] == 1

    client.patch(
        "/api/v1/admin/settings",
        headers=ADMIN_HEADERS,
        json={"generationCostCredits": 5},
    )

    assert client.get("/api/v1/admin/settings", headers=ADMIN_HEADERS).json()[
        "generationCostCredits"
    ] == 5


def test_the_new_cost_takes_effect_on_the_next_generation(client: TestClient) -> None:
    """Read at charge time, so there is no cache to go stale."""
    setup(client, credits=20)
    client.patch(
        "/api/v1/admin/settings",
        headers=ADMIN_HEADERS,
        json={"generationCostCredits": 5},
    )

    client.post("/api/v1/projects", headers=USER_HEADERS, json={"prompt": "a dragon"})

    assert balance(client) == 15


def test_a_cost_below_one_is_refused(client: TestClient) -> None:
    setup(client)

    response = client.patch(
        "/api/v1/admin/settings",
        headers=ADMIN_HEADERS,
        json={"generationCostCredits": 0},
    )

    # The app maps validation failures onto its own 400 envelope rather than
    # FastAPI's bare 422, so the client sees one error shape everywhere.
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_changing_the_cost_is_audited(client: TestClient) -> None:
    setup(client)
    client.patch(
        "/api/v1/admin/settings",
        headers=ADMIN_HEADERS,
        json={"generationCostCredits": 3},
    )

    assert "settings.update" in audit_actions(client)


# --- packages ----------------------------------------------------------------


def test_an_admin_sees_inactive_packages_too(client: TestClient) -> None:
    """A package you cannot see is a package you cannot re-enable."""
    setup(client)
    with client.app.state.database.connect() as connection:
        connection.execute("UPDATE credit_packages SET is_active = 0 WHERE name = 'Studio'")

    admin_names = [
        row["name"]
        for row in client.get(
            "/api/v1/admin/credit-packages", headers=ADMIN_HEADERS
        ).json()["items"]
    ]
    user_names = [
        row["name"]
        for row in client.get("/api/v1/credit-packages", headers=USER_HEADERS).json()["items"]
    ]

    assert "Studio" in admin_names
    assert "Studio" not in user_names


def test_an_admin_can_create_a_package(client: TestClient) -> None:
    setup(client)

    response = client.post(
        "/api/v1/admin/credit-packages",
        headers=ADMIN_HEADERS,
        json={"name": "Mega", "credits": 500, "priceVnd": 700000, "sortOrder": 9},
    )

    assert response.status_code == 201
    assert response.json()["credits"] == 500
    assert response.json()["isActive"] is True
    assert "package.create" in audit_actions(client)


def test_an_admin_can_take_a_package_off_sale(client: TestClient) -> None:
    setup(client)
    package = client.get(
        "/api/v1/admin/credit-packages", headers=ADMIN_HEADERS
    ).json()["items"][0]

    response = client.patch(
        f"/api/v1/admin/credit-packages/{package['id']}",
        headers=ADMIN_HEADERS,
        json={"isActive": False},
    )

    assert response.status_code == 200
    assert response.json()["isActive"] is False
    names = [
        row["name"]
        for row in client.get("/api/v1/credit-packages", headers=USER_HEADERS).json()["items"]
    ]
    assert package["name"] not in names


# --- events ------------------------------------------------------------------


def event_payload(**overrides) -> dict:
    payload = {
        "code": "FLASH",
        "name": "Flash sale",
        "kind": "grant",
        "bonusCredits": 25,
        "recurrence": "once",
        "startsAt": "2026-08-01T00:00:00Z",
        "endsAt": "2027-01-01T00:00:00Z",
        "maxClaims": 100,
    }
    payload.update(overrides)
    return payload


def test_an_admin_can_create_a_promotion(client: TestClient) -> None:
    """Brief §3: window, conditions, credits granted, signup cap, status."""
    setup(client)

    response = client.post(
        "/api/v1/admin/events", headers=ADMIN_HEADERS, json=event_payload()
    )

    assert response.status_code == 201
    body = response.json()
    assert body["bonusCredits"] == 25
    assert body["maxClaims"] == 100
    assert body["isActive"] is True
    assert "event.create" in audit_actions(client)


def test_a_created_promotion_is_immediately_claimable(client: TestClient) -> None:
    setup(client)
    created = client.post(
        "/api/v1/admin/events", headers=ADMIN_HEADERS, json=event_payload()
    ).json()

    claim = client.post(
        f"/api/v1/events/{created['id']}/claim", headers=USER_HEADERS
    )

    assert claim.status_code == 200
    assert claim.json()["creditsGranted"] == 25
    assert balance(client) == 25


def test_a_grant_without_credits_is_refused_with_a_usable_message(
    client: TestClient,
) -> None:
    """The CHECK constraint would refuse it too, but not by naming the field."""
    setup(client)

    response = client.post(
        "/api/v1/admin/events",
        headers=ADMIN_HEADERS,
        json=event_payload(bonusCredits=None),
    )

    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == "bonusCredits"


def test_an_event_ending_before_it_starts_is_refused(client: TestClient) -> None:
    setup(client)

    response = client.post(
        "/api/v1/admin/events",
        headers=ADMIN_HEADERS,
        json=event_payload(
            startsAt="2027-01-01T00:00:00Z", endsAt="2026-01-01T00:00:00Z"
        ),
    )

    assert response.status_code == 400


def test_an_admin_can_create_a_hot_hours_discount(client: TestClient) -> None:
    setup(client)

    response = client.post(
        "/api/v1/admin/events",
        headers=ADMIN_HEADERS,
        json=event_payload(
            code="HOT2", kind="discount", bonusCredits=None, discountPercent=30,
            recurrence="daily", activeFromMinute=1200, activeToMinute=1320,
            maxClaims=None,
        ),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["discountPercent"] == 30
    assert body["activeFromMinute"] == 1200


def test_an_admin_can_switch_a_promotion_off(client: TestClient) -> None:
    setup(client)
    created = client.post(
        "/api/v1/admin/events", headers=ADMIN_HEADERS, json=event_payload()
    ).json()

    client.patch(
        f"/api/v1/admin/events/{created['id']}",
        headers=ADMIN_HEADERS,
        json={"isActive": False},
    )

    claim = client.post(f"/api/v1/events/{created['id']}/claim", headers=USER_HEADERS)
    assert claim.status_code == 409
    assert "event.update" in audit_actions(client)


def test_an_admin_sees_who_claimed(client: TestClient) -> None:
    """Brief §3: "hiệu quả các đợt khuyến mãi"."""
    setup(client)
    created = client.post(
        "/api/v1/admin/events", headers=ADMIN_HEADERS, json=event_payload()
    ).json()
    client.post(f"/api/v1/events/{created['id']}/claim", headers=USER_HEADERS)

    body = client.get(
        f"/api/v1/admin/events/{created['id']}/claims", headers=ADMIN_HEADERS
    ).json()

    assert body["total"] == 1
    assert body["items"][0]["userId"] == USER_A
    assert body["items"][0]["creditsGranted"] == 25


def test_claims_for_an_unknown_event_are_not_found(client: TestClient) -> None:
    setup(client)

    response = client.get(
        "/api/v1/admin/events/00000000-0000-4000-8000-0000000000ff/claims",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 404


# --- transactions, payments and projects -------------------------------------


def test_an_admin_sees_every_users_transactions(client: TestClient) -> None:
    setup(client, credits=10)
    other = "20000000-0000-4000-8000-000000000002"
    client.app.state.database.upsert_user(other, email="b@example.com")
    client.app.state.credit_service.grant(other, 7, reason="event_grant")

    items = client.get(
        "/api/v1/admin/credit-transactions", headers=ADMIN_HEADERS
    ).json()["items"]

    owners = {row["userId"] for row in items}
    assert owners == {USER_A, other}


def test_admin_transactions_can_be_filtered_to_one_user(client: TestClient) -> None:
    setup(client, credits=10)
    other = "20000000-0000-4000-8000-000000000002"
    client.app.state.database.upsert_user(other, email="b@example.com")
    client.app.state.credit_service.grant(other, 7, reason="event_grant")

    items = client.get(
        f"/api/v1/admin/credit-transactions?userId={other}", headers=ADMIN_HEADERS
    ).json()["items"]

    assert {row["userId"] for row in items} == {other}


def test_an_admin_sees_payments(client: TestClient) -> None:
    setup(client)
    package = client.get("/api/v1/credit-packages", headers=USER_HEADERS).json()["items"][0]
    client.post(
        "/api/v1/payments",
        headers={"Idempotency-Key": "11111111-1111-4111-8111-aaaaaaaaaaaa", **USER_HEADERS},
        json={"packageId": package["id"]},
    )

    items = client.get("/api/v1/admin/payments", headers=ADMIN_HEADERS).json()["items"]

    assert len(items) == 1
    assert items[0]["userId"] == USER_A
    assert items[0]["status"] == "completed"
    # ADR-010: the row says the money was simulated.
    assert items[0]["method"] == "simulated"


def test_an_admin_sees_every_users_projects(client: TestClient) -> None:
    setup(client, credits=10)
    other = "20000000-0000-4000-8000-000000000002"
    client.app.state.database.upsert_user(other, email="b@example.com")
    client.app.state.credit_service.grant(other, 10, reason="purchase")
    client.post("/api/v1/projects", headers=USER_HEADERS, json={"prompt": "mine"})
    client.post(
        "/api/v1/projects", headers={"X-Debug-User-Id": other}, json={"prompt": "theirs"}
    )

    items = client.get("/api/v1/admin/projects", headers=ADMIN_HEADERS).json()["items"]

    assert len(items) == 2
    # A user still sees only their own.
    own = client.get("/api/v1/projects", headers=USER_HEADERS).json()["items"]
    assert len(own) == 1


def test_admin_projects_filter_by_status(client: TestClient) -> None:
    setup(client, credits=10)
    client.post("/api/v1/projects", headers=USER_HEADERS, json={"prompt": "one"})

    pending = client.get(
        "/api/v1/admin/projects?status=pending", headers=ADMIN_HEADERS
    ).json()["items"]
    completed = client.get(
        "/api/v1/admin/projects?status=completed", headers=ADMIN_HEADERS
    ).json()["items"]

    assert len(pending) == 1
    assert completed == []


def test_every_new_admin_endpoint_refuses_a_normal_user(client: TestClient) -> None:
    """One place to notice if a route is ever added without a role gate."""
    setup(client, credits=5)

    gets = [
        "/api/v1/admin/credit-transactions",
        "/api/v1/admin/settings",
        "/api/v1/admin/credit-packages",
        "/api/v1/admin/events",
        "/api/v1/admin/payments",
        "/api/v1/admin/projects",
    ]
    for path in gets:
        assert client.get(path, headers=USER_HEADERS).status_code == 403, path

    assert client.patch(
        "/api/v1/admin/settings", headers=USER_HEADERS,
        json={"generationCostCredits": 1},
    ).status_code == 403
    assert client.post(
        "/api/v1/admin/events", headers=USER_HEADERS, json=event_payload()
    ).status_code == 403
    assert client.post(
        "/api/v1/admin/credit-packages", headers=USER_HEADERS,
        json={"name": "X", "credits": 1, "priceVnd": 1},
    ).status_code == 403
