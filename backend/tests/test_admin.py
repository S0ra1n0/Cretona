from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import USER_A, USER_B, _seed_credits

ADMIN_ID = "30000000-0000-4000-8000-000000000003"
ADMIN_HEADERS = {"X-Debug-User-Id": ADMIN_ID}
USER_HEADERS = {"X-Debug-User-Id": USER_A}


@pytest.fixture
def seeded(client: TestClient) -> TestClient:
    database = client.app.state.database
    database.upsert_user(
        ADMIN_ID,
        email="admin@example.com",
        username="theadmin",
        role="admin",
        created_at="2026-01-03T00:00:00Z",
    )
    database.upsert_user(
        USER_A,
        email="alice@example.com",
        username="alice",
        created_at="2026-01-02T00:00:00Z",
    )
    database.upsert_user(
        USER_B,
        email="bob@example.com",
        username="bob",
        is_disabled=True,
        created_at="2026-01-01T00:00:00Z",
    )
    # A provisioned account can be charged for a generation (S-05); these tests
    # create projects and are not about billing.
    _seed_credits(client, USER_A, USER_B)
    return client


# --- authorization ----------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/admin/users"),
        ("PATCH", f"/api/v1/admin/users/{USER_B}"),
        ("GET", "/api/v1/admin/stats"),
    ],
)
def test_non_admin_is_forbidden(seeded: TestClient, method: str, path: str) -> None:
    response = seeded.request(method, path, headers=USER_HEADERS, json={"isDisabled": True})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_admin_endpoints_require_authentication(supabase_client: TestClient) -> None:
    assert supabase_client.get("/api/v1/admin/users").status_code == 401


def test_role_comes_from_the_database_not_a_header(seeded: TestClient) -> None:
    # A caller asserting admin-ness via a header they control gets nowhere.
    response = seeded.get(
        "/api/v1/admin/users",
        headers={**USER_HEADERS, "X-Role": "admin", "role": "admin"},
    )

    assert response.status_code == 403


# --- listing ----------------------------------------------------------------


def test_admin_can_list_users_newest_first(seeded: TestClient) -> None:
    body = seeded.get("/api/v1/admin/users", headers=ADMIN_HEADERS).json()

    assert [item["id"] for item in body["items"]] == [ADMIN_ID, USER_A, USER_B]
    assert body["items"][0]["role"] == "admin"


def test_search_matches_email_and_username(seeded: TestClient) -> None:
    by_email = seeded.get("/api/v1/admin/users?q=alice@", headers=ADMIN_HEADERS).json()
    by_username = seeded.get("/api/v1/admin/users?q=BOB", headers=ADMIN_HEADERS).json()

    assert [item["id"] for item in by_email["items"]] == [USER_A]
    # Search is case-insensitive.
    assert [item["id"] for item in by_username["items"]] == [USER_B]


def test_filters_by_role_and_disabled_state(seeded: TestClient) -> None:
    admins = seeded.get("/api/v1/admin/users?role=admin", headers=ADMIN_HEADERS).json()
    disabled = seeded.get("/api/v1/admin/users?isDisabled=true", headers=ADMIN_HEADERS).json()

    assert [item["id"] for item in admins["items"]] == [ADMIN_ID]
    assert [item["id"] for item in disabled["items"]] == [USER_B]


def test_listing_is_cursor_paginated(seeded: TestClient) -> None:
    first = seeded.get("/api/v1/admin/users?limit=2", headers=ADMIN_HEADERS).json()
    assert len(first["items"]) == 2
    assert first["page"]["hasMore"] is True

    second = seeded.get(
        f"/api/v1/admin/users?limit=2&cursor={first['page']['nextCursor']}",
        headers=ADMIN_HEADERS,
    ).json()

    assert len(second["items"]) == 1
    assert second["page"]["hasMore"] is False
    ids = {item["id"] for item in first["items"] + second["items"]}
    assert ids == {ADMIN_ID, USER_A, USER_B}


def test_project_count_is_reported(seeded: TestClient) -> None:
    seeded.post("/api/v1/projects", headers=USER_HEADERS, json={"prompt": "one"})
    seeded.post("/api/v1/projects", headers=USER_HEADERS, json={"prompt": "two"})

    body = seeded.get("/api/v1/admin/users?q=alice", headers=ADMIN_HEADERS).json()

    assert body["items"][0]["projectCount"] == 2


def test_invalid_cursor_is_a_validation_error(seeded: TestClient) -> None:
    response = seeded.get("/api/v1/admin/users?cursor=%%%", headers=ADMIN_HEADERS)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --- updating ---------------------------------------------------------------


def test_admin_can_promote_and_disable(seeded: TestClient) -> None:
    promoted = seeded.patch(
        f"/api/v1/admin/users/{USER_A}",
        headers=ADMIN_HEADERS,
        json={"role": "admin", "isDisabled": True},
    )

    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"
    assert promoted.json()["isDisabled"] is True


def test_admin_cannot_modify_themselves(seeded: TestClient) -> None:
    # FR-4.6: otherwise an admin can lock themselves out, or demote the last
    # admin and leave nobody able to get back in.
    response = seeded.patch(
        f"/api/v1/admin/users/{ADMIN_ID}",
        headers=ADMIN_HEADERS,
        json={"isDisabled": True},
    )

    assert response.status_code == 403
    assert "your own" in response.json()["error"]["message"]


def test_unknown_user_is_not_found(seeded: TestClient) -> None:
    response = seeded.patch(
        "/api/v1/admin/users/99999999-0000-4000-8000-000000000009",
        headers=ADMIN_HEADERS,
        json={"isDisabled": True},
    )

    assert response.status_code == 404


def test_empty_update_is_rejected(seeded: TestClient) -> None:
    response = seeded.patch(
        f"/api/v1/admin/users/{USER_A}",
        headers=ADMIN_HEADERS,
        json={},
    )

    assert response.status_code == 400


def test_unknown_role_is_rejected(seeded: TestClient) -> None:
    response = seeded.patch(
        f"/api/v1/admin/users/{USER_A}",
        headers=ADMIN_HEADERS,
        json={"role": "superuser"},
    )

    assert response.status_code == 400


def test_disabling_a_user_takes_effect_immediately(seeded: TestClient) -> None:
    seeded.patch(
        f"/api/v1/admin/users/{USER_A}",
        headers=ADMIN_HEADERS,
        json={"isDisabled": True},
    )

    # Dev mode injects identity without a disabled check, so the database is
    # the observable surface here.
    assert seeded.app.state.database.get_user(USER_A)["is_disabled"] is True


# --- stats ------------------------------------------------------------------


def test_stats_reports_totals_and_breakdowns(seeded: TestClient) -> None:
    created = seeded.post(
        "/api/v1/projects", headers=USER_HEADERS, json={"prompt": "counted"}
    ).json()
    seeded.get(f"/api/v1/projects/{created['id']}", headers=USER_HEADERS)
    seeded.get(f"/api/v1/projects/{created['id']}", headers=USER_HEADERS)

    body = seeded.get("/api/v1/admin/stats", headers=ADMIN_HEADERS).json()

    assert body["totals"]["users"] == 3
    assert body["totals"]["activeUsers"] == 2
    assert body["totals"]["projects"] == 1
    assert body["projectsByStatus"]["completed"] == 1
    assert body["projectsByProvider"]["fake"] == 1
    assert set(body["projectsByStatus"]) == {"pending", "generating", "completed", "failed"}


def test_failure_rate_counts_only_finished_work(seeded: TestClient) -> None:
    def drive(prompt: str) -> None:
        created = seeded.post(
            "/api/v1/projects", headers=USER_HEADERS, json={"prompt": prompt}
        ).json()
        seeded.get(f"/api/v1/projects/{created['id']}", headers=USER_HEADERS)
        seeded.get(f"/api/v1/projects/{created['id']}", headers=USER_HEADERS)

    drive("good one")
    drive("fail:provider_error bad one")
    # Left pending, so it must not dilute the rate.
    seeded.post("/api/v1/projects", headers=USER_HEADERS, json={"prompt": "in flight"})

    body: dict[str, Any] = seeded.get("/api/v1/admin/stats", headers=ADMIN_HEADERS).json()

    assert body["failureRate"] == 0.5


def test_daily_series_is_bucketed_by_day(seeded: TestClient) -> None:
    seeded.post("/api/v1/projects", headers=USER_HEADERS, json={"prompt": "today"})

    body = seeded.get("/api/v1/admin/stats?days=7", headers=ADMIN_HEADERS).json()

    assert len(body["daily"]) == 1
    assert len(body["daily"][0]["date"]) == 10
    assert body["daily"][0]["created"] == 1


def test_admin_can_read_project_generation_logs(seeded: TestClient) -> None:
    created = seeded.post(
        "/api/v1/projects", headers=USER_HEADERS, json={"prompt": "log test"}
    ).json()
    pid = created["id"]

    logs = seeded.get(f"/api/v1/admin/projects/{pid}/logs", headers=ADMIN_HEADERS)
    assert logs.status_code == 200
    data = logs.json()
    assert "items" in data
    assert len(data["items"]) >= 1
    assert data["items"][0]["projectId"] == pid
    assert data["items"][0]["event"] == "submit"


def test_admin_can_trigger_thumbnail_backfill(seeded: TestClient) -> None:
    res = seeded.post("/api/v1/admin/thumbnails/backfill", headers=ADMIN_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "backfilled" in data
    assert "processed" in data


def test_admin_can_list_audit_logs(seeded: TestClient) -> None:
    # 1. Update user
    update_res = seeded.patch(
        f"/api/v1/admin/users/{USER_A}",
        headers=ADMIN_HEADERS,
        json={"role": "admin"},
    )
    assert update_res.status_code == 200

    # 2. Trigger backfill
    backfill_res = seeded.post("/api/v1/admin/thumbnails/backfill", headers=ADMIN_HEADERS)
    assert backfill_res.status_code == 200

    # 3. Query audit logs
    audit_res = seeded.get("/api/v1/admin/audit-logs", headers=ADMIN_HEADERS)
    assert audit_res.status_code == 200
    body = audit_res.json()
    assert "items" in body
    assert len(body["items"]) >= 2
    actions = [item["action"] for item in body["items"]]
    assert "user_updated" in actions
    assert "thumbnails_backfilled" in actions

    # 4. Filter by action
    filtered = seeded.get(
        "/api/v1/admin/audit-logs?action=user_updated", headers=ADMIN_HEADERS
    ).json()
    assert len(filtered["items"]) == 1
    assert filtered["items"][0]["action"] == "user_updated"
    assert filtered["items"][0]["targetId"] == USER_A

    # 5. Non-admin forbidden (demote USER_A back to user)
    seeded.patch(
        f"/api/v1/admin/users/{USER_A}",
        headers=ADMIN_HEADERS,
        json={"role": "user"},
    )
    forbidden = seeded.get("/api/v1/admin/audit-logs", headers=USER_HEADERS)
    assert forbidden.status_code == 403


# --- T2-5: the audit row and the change it describes ------------------------


def test_an_unwritable_audit_row_rolls_back_the_privilege_change(
    seeded: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gap this closes.

    The audit write used to happen after the mutation had already committed,
    so a failing insert left a promoted admin with no record of who promoted
    them. Sharing one transaction means the promotion fails too.
    """
    database = seeded.app.state.database

    def refuse(connection: Any, entry: Any) -> None:
        raise RuntimeError("audit table is unavailable")

    monkeypatch.setattr(type(database), "_insert_audit_log", staticmethod(refuse))

    response = seeded.patch(
        f"/api/v1/admin/users/{USER_A}",
        headers=ADMIN_HEADERS,
        json={"role": "admin"},
    )

    assert response.status_code == 500
    # The change was refused, not silently kept.
    assert database.get_user(USER_A)["role"] == "user"


def test_a_successful_change_is_recorded_with_it(seeded: TestClient) -> None:
    database = seeded.app.state.database

    seeded.patch(
        f"/api/v1/admin/users/{USER_A}",
        headers=ADMIN_HEADERS,
        json={"role": "admin"},
    )

    rows, _ = database.list_audit_logs(limit=50, cursor=None, action="user_updated", actor_id=None)
    assert [row["target_id"] for row in rows] == [USER_A]
    assert database.get_user(USER_A)["role"] == "admin"


def test_admin_metrics_endpoint(seeded: TestClient) -> None:
    res = seeded.get("/api/v1/admin/metrics", headers=ADMIN_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "uptimeSeconds" in data
    assert "activeJobs" in data
    assert "completedJobs" in data
    assert "failedJobs" in data
    assert "memoryRssMb" in data
    assert data["databaseStatus"] == "healthy"
    assert data["databaseBackend"] == "sqlite"
    assert data["storageBackend"] == "local"


def test_admin_metrics_forbidden_for_regular_user(seeded: TestClient) -> None:
    res = seeded.get("/api/v1/admin/metrics", headers={"X-Debug-User-Id": USER_A})
    assert res.status_code == 403


def test_prometheus_metrics_endpoint(seeded: TestClient) -> None:
    res = seeded.get("/api/v1/metrics", headers=ADMIN_HEADERS)
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    body = res.text
    assert "cretona_uptime_seconds" in body
    assert "cretona_memory_rss_bytes" in body
    assert "cretona_video_jobs_total" in body
    assert "cretona_active_jobs" in body
    assert "cretona_database_status" in body
    assert "cretona_storage_backend" in body


def test_prometheus_metrics_forbidden_for_regular_user(seeded: TestClient) -> None:
    res = seeded.get("/api/v1/metrics", headers={"X-Debug-User-Id": USER_A})
    assert res.status_code == 403
