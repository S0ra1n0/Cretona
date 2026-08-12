from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.errors import AppError
from app.schemas import AdminUser, AdminUserPage, AdminUserUpdate, PageInfo, StatsResponse

logger = logging.getLogger("cretona.admin")


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

        current = self.database.get_user(target_id)
        if current is None:
            raise AppError(404, "NOT_FOUND", "User not found.")

        if self._would_remove_the_last_admin(current, payload):
            raise AppError(
                409,
                "CONFLICT",
                "This is the last enabled admin. Promote another admin first.",
            )

        row = self.database.update_user_flags(
            target_id,
            role=payload.role,
            is_disabled=payload.is_disabled,
        )
        if row is None:
            raise AppError(404, "NOT_FOUND", "User not found.")

        # Privilege changes are the actions most worth reconstructing later.
        logger.info(
            "admin_user_updated",
            extra={
                "actorId": acting_admin_id,
                "targetId": target_id,
                "roleFrom": current.get("role"),
                "roleTo": payload.role,
                "disabledFrom": bool(current.get("is_disabled")),
                "disabledTo": payload.is_disabled,
            },
        )
        return to_admin_user(row)

    def _would_remove_the_last_admin(
        self,
        current: dict[str, Any],
        payload: AdminUserUpdate,
    ) -> bool:
        """Refuse a change that leaves nobody able to administer the project.

        Over HTTP this is unreachable, and deliberately so: to strip the last
        enabled admin the target must be someone other than the actor, which
        means the actor is not an enabled admin, which means `require_admin`
        already refused. The self-modification rule above is what actually
        preserves the invariant on that path.

        It stays as a service-level invariant because AdminService is a plain
        object that a script or migration could call without going through the
        role gate. Tested at that level rather than through the API, because
        pretending otherwise would be testing a branch that cannot execute.
        """
        if current.get("role") != "admin" or current.get("is_disabled"):
            return False

        removes_admin = payload.is_disabled is True or (
            payload.role is not None and payload.role != "admin"
        )
        if not removes_admin:
            return False
        return self.database.count_enabled_admins() <= 1

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
