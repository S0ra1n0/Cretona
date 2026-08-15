from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.errors import AppError
from app.schemas import (
    AdminAuditLog,
    AdminAuditLogPage,
    AdminLogItem,
    AdminUser,
    AdminUserPage,
    AdminUserUpdate,
    BackfillResponse,
    PageInfo,
    StatsResponse,
)

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
        now_str = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        self.database.insert_audit_log(
            id=str(uuid.uuid4()),
            actor_id=acting_admin_id,
            action="user_updated",
            target_type="user",
            target_id=target_id,
            details={
                "roleFrom": current.get("role"),
                "roleTo": payload.role,
                "disabledFrom": bool(current.get("is_disabled")),
                "disabledTo": payload.is_disabled,
            },
            created_at=now_str,
        )
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

    def get_generation_logs(self, project_id: str) -> list[AdminLogItem]:
        rows = self.database.generation_logs(project_id)
        return [
            AdminLogItem(
                id=row.get("id"),
                project_id=row["project_id"],
                provider=row["provider"],
                request_id=row.get("request_id"),
                event=row["event"],
                request=row.get("request"),
                response=row.get("response"),
                http_status=row.get("http_status"),
                created_at=row.get("created_at") or "",
            )
            for row in rows
        ]

    def backfill_thumbnails(
        self,
        storage: Any,
        thumbnails: Any,
        acting_admin_id: str | None = None,
    ) -> BackfillResponse:
        rows = self.database.list_projects_missing_thumbnails()
        backfilled = 0
        for row in rows:
            owner_id = row["owner_id"]
            video_path = row.get("video_path")
            if not video_path:
                continue
            source = storage.local_video_path(video_path)
            if source is None or not source.exists():
                continue
            target_path = storage.store_thumbnail_path(owner_id, row["id"])
            if getattr(storage, "name", "") == "supabase":
                temp_target = source.parent / f"thumb_bf_{row['id']}.jpg"
                try:
                    if not thumbnails.extract(source, temp_target):
                        continue
                    store_fn = getattr(storage, "store_thumbnail", None)
                    if store_fn is not None:
                        res = store_fn(owner_id, row["id"], temp_target.read_bytes())
                        if res:
                            self.database.update_project(
                                row["id"], owner_id, {"thumbnail_path": res}
                            )
                            backfilled += 1
                finally:
                    temp_target.unlink(missing_ok=True)
            else:
                target = source.parent / "thumbnail.jpg"
                if thumbnails.extract(source, target):
                    self.database.update_project(
                        row["id"], owner_id, {"thumbnail_path": target_path}
                    )
                    backfilled += 1

        if acting_admin_id:
            now_str = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            self.database.insert_audit_log(
                id=str(uuid.uuid4()),
                actor_id=acting_admin_id,
                action="thumbnails_backfilled",
                target_type="system",
                details={"backfilled": backfilled, "processed": len(rows)},
                created_at=now_str,
            )

        return BackfillResponse(backfilled=backfilled, processed=len(rows))

    def list_audit_logs(
        self,
        *,
        limit: int,
        cursor: str | None,
        action: str | None,
        actor_id: str | None,
    ) -> AdminAuditLogPage:
        try:
            rows, next_cursor = self.database.list_audit_logs(
                limit=limit,
                cursor=cursor,
                action=action,
                actor_id=actor_id,
            )
        except ValueError as exc:
            raise AppError(
                400,
                "VALIDATION_ERROR",
                "The pagination cursor is invalid.",
                [{"field": "query.cursor", "issue": "invalid_cursor"}],
            ) from exc

        return AdminAuditLogPage(
            items=[
                AdminAuditLog(
                    id=row["id"],
                    actor_id=row["actor_id"],
                    action=row["action"],
                    target_type=row["target_type"],
                    target_id=row.get("target_id"),
                    details=row.get("details"),
                    created_at=row["created_at"],
                )
                for row in rows
            ],
            page=PageInfo(next_cursor=next_cursor, has_more=next_cursor is not None),
        )


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
