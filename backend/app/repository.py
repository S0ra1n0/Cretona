from __future__ import annotations

import base64
import json
from typing import Any, Protocol, runtime_checkable

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

    def get_user(self, user_id: str) -> dict[str, Any] | None: ...


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
) -> dict[str, Any]:
    """Shape admin statistics identically on either backend.

    Both adapters run their own dialect-specific aggregation and then hand the
    rows here, so a difference in SQL cannot become a difference in contract.
    """
    status_counts = {row["status"]: int(row["total"]) for row in by_status}
    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)
    finished = completed + failed

    return {
        "totals": {
            "users": int(totals["users"]),
            "activeUsers": int(totals["active_users"]),
            "projects": int(totals["projects"]),
        },
        "projectsByStatus": {status: status_counts.get(status, 0) for status in STATUSES},
        "projectsByProvider": {row["provider"]: int(row["total"]) for row in by_provider},
        # The denominator is finished generations, not all of them: counting
        # in-flight work as a success would make the rate drift with load.
        "failureRate": 0.0 if finished == 0 else round(failed / finished, 4),
        "daily": [
            {
                "date": str(row["date"])[:10],
                "created": int(row["created"] or 0),
                "completed": int(row["completed"] or 0),
                "failed": int(row["failed"] or 0),
            }
            for row in daily
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
