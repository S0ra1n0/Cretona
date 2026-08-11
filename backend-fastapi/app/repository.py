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
        "updated_at",
        "completed_at",
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
