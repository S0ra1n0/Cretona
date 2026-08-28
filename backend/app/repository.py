from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class AuditEntry:
    """An audit row to be written with the mutation it describes.

    Passed into a mutation rather than written after it, so the two either both
    land or neither does. Logging a failed audit write and carrying on meant an
    admin action could succeed with no trail at all (T2-5).
    """

    id: str
    actor_id: str
    action: str
    target_type: str
    target_id: str | None
    details: Any
    created_at: str


# Row dictionaries are the stable currency between an adapter and the service
# layer. Adapters translate their own column names onto these keys, so the
# service never learns which database it is talking to. Postgres calls the
# owner `user_id` and the table `video_projects`; SQLite calls them `owner_id`
# and `projects`. Neither spelling reaches ProjectService.
ROW_KEYS = (
    "id",
    "owner_id",
    "title",
    "prompt",
    "image_path",
    "provider",
    "status",
    "provider_job_id",
    "error_code",
    "error_message",
    "duration_seconds",
    "aspect_ratio",
    "video_path",
    "thumbnail_path",
    "poll_count",
    "attempt_count",
    "idempotency_key",
    "started_at",
    "progress_percent",
    "step_message",
    "created_at",
    "updated_at",
    "completed_at",
)

# Columns a running job is allowed to change. `owner_id`, `created_at`, and the
# generation inputs are not here: a project's identity and inputs are fixed at
# creation, so an update cannot silently reassign ownership.
MUTABLE_COLUMNS = frozenset(
    {
        "status",
        "provider_job_id",
        "error_code",
        "error_message",
        "duration_seconds",
        "video_path",
        "thumbnail_path",
        "poll_count",
        "attempt_count",
        "progress_percent",
        "step_message",
        "updated_at",
        "completed_at",
        # Reset on every retry so each attempt gets a full timeout budget.
        "started_at",
    }
)


@runtime_checkable
class ProjectRepository(Protocol):
    """What ProjectService needs from a database, and nothing more."""

    def initialize(self) -> None: ...

    def create_project(self, values: dict[str, Any]) -> tuple[dict[str, Any], bool]: ...

    def find_by_idempotency(self, owner_id: str, key: str) -> dict[str, Any] | None: ...

    def get_project(self, project_id: str, owner_id: str) -> dict[str, Any] | None: ...

    def update_project(
        self,
        project_id: str,
        owner_id: str,
        values: dict[str, Any],
        *,
        expected_status: str | None = None,
    ) -> dict[str, Any] | None: ...

    def list_projects(
        self,
        owner_id: str,
        *,
        limit: int,
        status: str | None,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]: ...

    def soft_delete_project(self, project_id: str, owner_id: str) -> bool: ...

    def claim_in_flight_projects(
        self,
        limit: int,
        *,
        owner: str,
        now: str,
        lease_until: str,
        providers: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_user(self, user_id: str) -> dict[str, Any] | None: ...


class InsufficientCreditsError(Exception):
    """A charge would drive a balance below zero.

    Raised by the repository rather than checked by the service, because the
    guard lives in the UPDATE's WHERE clause: a service that read the balance
    and then wrote it would lose to a concurrent charge.
    """

    def __init__(self, user_id: str) -> None:
        super().__init__(f"Insufficient credits for user {user_id}.")
        self.user_id = user_id


class UnknownUserError(Exception):
    """A credit operation named a user that does not exist."""

    def __init__(self, user_id: str) -> None:
        super().__init__(f"Unknown user {user_id}.")
        self.user_id = user_id


class UsernameTakenError(Exception):
    """A username collided with the unique index."""

    def __init__(self, username: str) -> None:
        super().__init__(f"Username already taken: {username}")
        self.username = username


STATUSES = ("pending", "generating", "completed", "failed")


def build_stats(
    totals: dict[str, Any],
    by_status: Any,
    by_provider: Any,
    daily: Any,
    daily_users: Any = (),
    daily_credits: Any = (),
    daily_revenue: Any = (),
    events: Any = (),
) -> dict[str, Any]:
    """Shape admin statistics identically on either backend.

    Both adapters run their own dialect-specific aggregation and then hand the
    rows here, so a difference in SQL cannot become a difference in contract.

    The daily series is assembled from four separate queries rather than one
    joined one. Joining them would drop a day on which credits moved but no
    project was created -- and a revenue chart with holes in it is worse than
    no chart, because it looks like data.
    """
    status_counts = {row["status"]: int(row["total"]) for row in by_status}
    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)
    finished = completed + failed

    def blank() -> dict[str, int]:
        return {
            "created": 0, "completed": 0, "failed": 0,
            "newUsers": 0, "creditsGranted": 0, "creditsUsed": 0, "revenueVnd": 0,
        }

    buckets: dict[str, dict[str, int]] = {}

    def bucket(value: Any) -> dict[str, int]:
        return buckets.setdefault(str(value)[:10], blank())

    for row in daily:
        entry = bucket(row["date"])
        entry["created"] = int(row["created"] or 0)
        entry["completed"] = int(row["completed"] or 0)
        entry["failed"] = int(row["failed"] or 0)

    for row in daily_users:
        bucket(row["date"])["newUsers"] = int(row["total"] or 0)

    for row in daily_credits:
        entry = bucket(row["date"])
        entry["creditsGranted"] = int(row["granted"] or 0)
        entry["creditsUsed"] = int(row["used"] or 0)

    for row in daily_revenue:
        bucket(row["date"])["revenueVnd"] = int(row["revenue"] or 0)

    return {
        "totals": {
            "users": int(totals["users"]),
            "activeUsers": int(totals["active_users"]),
            "projects": int(totals["projects"]),
            # Brief §3: "Credit đã cấp/đã sử dụng, doanh thu bán Credit".
            "creditsGranted": int(totals.get("credits_granted") or 0),
            "creditsUsed": int(totals.get("credits_used") or 0),
            # Simulated revenue -- no real money moves (ADR-010). The dashboard
            # labels it as such where it is displayed.
            "revenueVnd": int(totals.get("revenue_vnd") or 0),
        },
        "projectsByStatus": {status: status_counts.get(status, 0) for status in STATUSES},
        "projectsByProvider": {row["provider"]: int(row["total"]) for row in by_provider},
        # The denominator is finished generations, not all of them: counting
        # in-flight work as a success would make the rate drift with load.
        "failureRate": 0.0 if finished == 0 else round(failed / finished, 4),
        "daily": [
            {"date": date, **buckets[date]}
            for date in sorted(buckets, reverse=True)
        ],
        "events": [
            {
                "eventId": str(row["id"]),
                "code": row["code"],
                "name": row["name"],
                "claims": int(row["claims"] or 0),
                "creditsGranted": int(row["credits_granted"] or 0),
                # None when uncapped, so the app shows "unlimited" rather than
                # a number that would have to mean two things.
                "remainingSlots": (
                    None if row["max_claims"] is None
                    else max(0, int(row["max_claims"]) - int(row["claims"] or 0))
                ),
            }
            for row in events
        ],
    }


def reject_immutable_columns(values: dict[str, Any]) -> None:
    unknown = set(values) - MUTABLE_COLUMNS
    if unknown:
        raise ValueError(f"Unsupported project columns: {sorted(unknown)}")


def encode_cursor(created_at: str, project_id: str) -> str:
    raw = json.dumps({"createdAt": created_at, "id": project_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    """Decode an opaque cursor, or raise ValueError.

    Keyset, not OFFSET: rows inserted while a user pages would shift an offset
    window and duplicate or skip items. The cursor carries the sort key plus the
    id as a tie-breaker, because created_at is not unique.
    """
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
        created_at = payload["createdAt"]
        project_id = payload["id"]
        if not isinstance(created_at, str) or not isinstance(project_id, str):
            raise TypeError
        return created_at, project_id
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid cursor") from exc
