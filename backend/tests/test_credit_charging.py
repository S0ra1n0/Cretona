"""Credits charged and refunded around a real generation (S-05).

`test_credits.py` covers the ledger in isolation. This covers the wiring: that
a generation actually costs something, that a failure gives it back, and that
neither happens twice.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import USER_A, _seed_credits

HEADERS = {"X-Debug-User-Id": USER_A}


def balance(client: TestClient) -> int:
    return client.app.state.credit_service.balance(USER_A)


def ledger(client: TestClient) -> list[dict]:
    rows, _ = client.app.state.credit_service.history(USER_A, limit=50)
    return rows


def create(client: TestClient, prompt: str = "a paper dragon", **kwargs):
    return client.post("/api/v1/projects", headers=HEADERS, json={"prompt": prompt}, **kwargs)


def funded(client: TestClient, amount: int = 10) -> TestClient:
    database = client.app.state.database
    database.upsert_user(USER_A, email="a@example.com")
    client.app.state.credit_service.grant(USER_A, amount, reason="purchase")
    return client


# --- charging ----------------------------------------------------------------


def test_a_generation_costs_a_credit(client: TestClient) -> None:
    funded(client, 10)

    assert create(client).status_code == 201
    assert balance(client) == 9

    charge = ledger(client)[0]
    assert charge["reason"] == "generation"
    assert charge["delta"] == -1
    assert charge["ref_type"] == "project"


def test_the_charge_names_the_project_it_paid_for(client: TestClient) -> None:
    funded(client, 10)
    project_id = create(client).json()["id"]

    charge = ledger(client)[0]
    assert charge["ref_id"] == project_id


def test_an_empty_balance_is_refused_with_402(client: TestClient) -> None:
    database = client.app.state.database
    database.upsert_user(USER_A, email="a@example.com")

    response = create(client)

    assert response.status_code == 402
    assert response.json()["error"]["code"] == "INSUFFICIENT_CREDITS"


def test_a_refusal_creates_no_project_and_no_ledger_row(client: TestClient) -> None:
    """The check runs before the row exists, so a refusal leaves nothing."""
    database = client.app.state.database
    database.upsert_user(USER_A, email="a@example.com")

    create(client)

    assert client.get("/api/v1/projects", headers=HEADERS).json()["items"] == []
    assert ledger(client) == []


def test_the_refusal_says_what_it_needed_and_what_was_there(client: TestClient) -> None:
    database = client.app.state.database
    database.upsert_user(USER_A, email="a@example.com")

    message = create(client).json()["error"]["message"]

    # A user who cannot pay needs to know the number and what to do about it,
    # not just that something was refused.
    assert "1 credits" in message
    assert "you have 0" in message
    assert "buy more credits" in message.lower()


def test_credits_are_separate_from_quota(client: TestClient) -> None:
    """QUOTA_EXCEEDED and INSUFFICIENT_CREDITS are different refusals.

    ADR-007's rolling limit still applies; credits do not replace it. A user
    with plenty of credits can still hit the rate of generation cap, and the
    app routes the two differently.
    """
    funded(client, 100)

    codes = set()
    for index in range(12):
        response = create(client, prompt=f"clip {index}")
        if response.status_code != 201:
            codes.add(response.json()["error"]["code"])

    # Which of the two bites first depends on the configured limits, and that
    # is not what this asserts. What matters is that a funded user is never
    # refused for money.
    assert codes
    assert "INSUFFICIENT_CREDITS" not in codes
    assert codes <= {"QUOTA_EXCEEDED", "RATE_LIMITED"}


# --- refunds -----------------------------------------------------------------


def test_cancelling_gives_the_credit_back(client: TestClient) -> None:
    funded(client, 10)
    project_id = create(client).json()["id"]
    assert balance(client) == 9

    cancelled = client.post(f"/api/v1/projects/{project_id}/cancel", headers=HEADERS)

    assert cancelled.status_code == 200
    assert balance(client) == 10

    refund = ledger(client)[0]
    assert refund["reason"] == "refund"
    assert refund["delta"] == 1
    assert refund["ref_id"] == project_id


def test_the_refund_is_recorded_not_just_applied(client: TestClient) -> None:
    """Section 2.2 requires the transaction history, not only the balance."""
    funded(client, 10)
    project_id = create(client).json()["id"]
    client.post(f"/api/v1/projects/{project_id}/cancel", headers=HEADERS)

    reasons = [row["reason"] for row in ledger(client)]

    assert reasons[:2] == ["refund", "generation"]


def test_cancelling_twice_refunds_once(client: TestClient) -> None:
    funded(client, 10)
    project_id = create(client).json()["id"]

    client.post(f"/api/v1/projects/{project_id}/cancel", headers=HEADERS)
    client.post(f"/api/v1/projects/{project_id}/cancel", headers=HEADERS)

    assert balance(client) == 10
    assert sum(1 for row in ledger(client) if row["reason"] == "refund") == 1


def test_a_completed_generation_keeps_the_charge(client: TestClient) -> None:
    """A refund is for failure. Success is what the credit paid for."""
    funded(client, 10)
    project_id = create(client).json()["id"]

    # The mock provider completes on the first read-driven advance.
    for _ in range(3):
        client.get(f"/api/v1/projects/{project_id}", headers=HEADERS)

    status = client.get(f"/api/v1/projects/{project_id}", headers=HEADERS).json()["status"]
    assert status == "completed"
    assert balance(client) == 9
    assert ledger(client)[0]["reason"] == "generation"


# --- idempotency -------------------------------------------------------------


def test_a_replayed_submission_charges_once(client: TestClient) -> None:
    """The same Idempotency-Key returns the same project and one charge."""
    funded(client, 10)
    key = {"Idempotency-Key": "11111111-1111-4111-8111-aaaaaaaaaaaa", **HEADERS}

    first = client.post("/api/v1/projects", headers=key, json={"prompt": "same"})
    second = client.post("/api/v1/projects", headers=key, json={"prompt": "same"})

    assert first.json()["id"] == second.json()["id"]
    assert balance(client) == 9
    assert sum(1 for row in ledger(client) if row["reason"] == "generation") == 1


# --- the signup bonus --------------------------------------------------------


def test_reading_the_profile_grants_the_signup_bonus(client: TestClient) -> None:
    """Section 2.1: an account created during a promotion gets its credits."""
    client.app.state.database.upsert_user(USER_A, email="a@example.com", username="a")

    assert balance(client) == 0
    client.get("/api/v1/me", headers=HEADERS)

    assert balance(client) == 5
    assert ledger(client)[0]["reason"] == "signup_bonus"


def test_the_signup_bonus_is_granted_once(client: TestClient) -> None:
    client.app.state.database.upsert_user(USER_A, email="a@example.com", username="a")

    for _ in range(4):
        client.get("/api/v1/me", headers=HEADERS)

    assert balance(client) == 5
    assert len(ledger(client)) == 1


def test_the_bonus_makes_a_new_account_able_to_generate(client: TestClient) -> None:
    """End to end: the gap that made a fresh account permanently unusable."""
    client.app.state.database.upsert_user(USER_A, email="a@example.com", username="a")
    client.get("/api/v1/me", headers=HEADERS)

    assert create(client).status_code == 201
    assert balance(client) == 4


# --- the ledger stays consistent ---------------------------------------------


def test_the_ledger_explains_the_balance_after_a_full_cycle(client: TestClient) -> None:
    funded(client, 10)
    _seed_credits(client, USER_A)  # a second grant, to make the arithmetic real

    first = create(client, "one").json()["id"]
    client.post(f"/api/v1/projects/{first}/cancel", headers=HEADERS)
    create(client, "two")

    assert client.app.state.database.ledger_drift() == []
