from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.errors import AppError
from app.schemas import AdminUser, AdminUserPage, AdminUserUpdate, PageInfo, StatsResponse


class AdminService:
    def __init__(self, database: Any) -> None:
        self.database = database

    def list_users(
        self,
        *,
        limit: int,
        cursor: str | None,
        query: str | None,
        role: str | None,
        is_disabled: bool | None,
    ) -> AdminUserPage:
        try:
            rows, next_cursor = self.database.list_users(
                limit=limit,
                cursor=cursor,
                query=query,
                role=role,
                is_disabled=is_disabled,
            )
        except ValueError as exc:
            raise AppError(
                400,
                "VALIDATION_ERROR",
                "The pagination cursor is invalid.",
                [{"field": "query.cursor", "issue": "invalid_cursor"}],
            ) from exc

        return AdminUserPage(
            items=[to_admin_user(row) for row in rows],
            page=PageInfo(nextCursor=next_cursor, hasMore=next_cursor is not None),
        )

    def update_user(
        self,
        acting_admin_id: str,
        target_id: str,
        payload: AdminUserUpdate,
    ) -> AdminUser:
        # FR-4.6. Without this an admin can lock themselves out, or demote the
        # last admin and leave the project with no way back in.
        if acting_admin_id == target_id:
            raise AppError(
                403,
                "FORBIDDEN",
                "You cannot change your own role or disable your own account.",
            )

        row = self.database.update_user_flags(
            target_id,
            role=payload.role,
            is_disabled=payload.is_disabled,
        )
        if row is None:
            raise AppError(404, "NOT_FOUND", "User not found.")
        return to_admin_user(row)

    def stats(self, days: int) -> StatsResponse:
        since = datetime.now(UTC) - timedelta(days=days)
        raw = self.database.admin_stats(since.isoformat().replace("+00:00", "Z"))
        return StatsResponse.model_validate(raw)


def to_admin_user(row: dict[str, Any]) -> AdminUser:
    return AdminUser(
        id=row["id"],
        email=row.get("email"),
        username=row.get("username"),
        role=row.get("role", "user"),
        isDisabled=bool(row.get("is_disabled")),
        projectCount=int(row.get("project_count") or 0),
        createdAt=row.get("created_at") or "",
    )
