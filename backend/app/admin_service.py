from __future__ import annotations

import logging
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.errors import AppError
from app.repository import AuditEntry
from app.schemas import (
    AdminAuditLog,
    AdminAuditLogPage,
    AdminLogItem,
    AdminMetricsResponse,
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

        # Privilege changes are the actions most worth reconstructing later, so
        # the trail is written with the change rather than after it: if the
        # audit row cannot be written, the change does not happen (T2-5).
        row = self.database.update_user_flags(
            target_id,
            role=payload.role,
            is_disabled=payload.is_disabled,
            audit=self._entry(
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
            ),
        )
        if row is None:
            raise AppError(404, "NOT_FOUND", "User not found.")

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
            downloaded: Path | None = None
            if source is None or not source.exists():
                # No local copy. That is the normal case for anything the Kaggle
                # worker produced: it uploads straight to Storage and the bytes
                # never touch this host, so `local_video_path` returning None
                # used to end the story and the video stayed thumbnail-less
                # forever. Fetch it instead.
                reader = getattr(storage, "read_video_bytes", None)
                payload = reader(video_path) if reader is not None else None
                if not payload:
                    continue
                downloaded = Path(tempfile.gettempdir()) / f"cretona_bf_{row['id']}.mp4"
                downloaded.write_bytes(payload)
                source = downloaded

            try:
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
            finally:
                # Whatever the branch did, a downloaded copy is scratch space.
                if downloaded is not None:
                    downloaded.unlink(missing_ok=True)

        if acting_admin_id:
            self._audit(
                actor_id=acting_admin_id,
                action="thumbnails_backfilled",
                target_type="system",
                details={"backfilled": backfilled, "processed": len(rows)},
            )

        return BackfillResponse(backfilled=backfilled, processed=len(rows))

    def get_system_metrics(
        self,
        storage: Any,
        start_time: float,
    ) -> AdminMetricsResponse:
        import os
        import time

        uptime = max(0.0, time.time() - start_time)

        # Process memory
        memory_mb = 45.0
        try:
            import psutil

            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / (1024 * 1024)
        except Exception:
            pass

        # Project status counts
        try:
            stats_raw = self.database.admin_stats("1970-01-01T00:00:00Z")
            status_dict = stats_raw.get("projects_by_status", {})
            active_jobs = status_dict.get("pending", 0) + status_dict.get("generating", 0)
            completed_jobs = status_dict.get("completed", 0)
            failed_jobs = status_dict.get("failed", 0)
        except Exception:
            active_jobs = 0
            completed_jobs = 0
            failed_jobs = 0

        db_backend = getattr(self.database, "backend", "sqlite")
        db_status = "healthy"
        try:
            if hasattr(self.database, "connect"):
                with self.database.connect() as conn:
                    conn.execute("SELECT 1").fetchone()
            elif hasattr(self.database, "pool"):
                with self.database.pool.connection() as conn:
                    conn.execute("SELECT 1").fetchone()
        except Exception:
            db_status = "unreachable"

        storage_name = getattr(storage, "name", "local")

        return AdminMetricsResponse(
            uptime_seconds=round(uptime, 1),
            active_jobs=active_jobs,
            completed_jobs=completed_jobs,
            failed_jobs=failed_jobs,
            memory_rss_mb=round(memory_mb, 2),
            database_backend=db_backend,
            database_status=db_status,
            storage_backend=storage_name,
        )

    @staticmethod
    def _entry(
        *,
        actor_id: str,
        action: str,
        target_type: str,
        details: dict[str, Any],
        target_id: str | None = None,
    ) -> AuditEntry:
        """An audit row for a mutation to write alongside itself."""
        return AuditEntry(
            id=str(uuid.uuid4()),
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    def _audit(
        self,
        *,
        actor_id: str,
        action: str,
        target_type: str,
        details: dict[str, Any],
        target_id: str | None = None,
    ) -> None:
        """Record an action that has already committed, without undoing it.

        Only for actions with no single transaction to join. The thumbnail
        backfill is the case: it commits one project at a time, so there is no
        moment at which the summary row could be atomic with "the mutation".
        Raising here would return 500 for work that actually happened, and an
        admin who retries on that basis is acting on a false picture.

        Single-row mutations do not use this. They pass an `AuditEntry` into
        the write itself, where the trail and the change share a transaction
        and the trade-off disappears (T2-5).

        The failure is logged at error level rather than swallowed quietly,
        because a gap in an audit trail is itself worth investigating.
        """
        entry = self._entry(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
        )
        try:
            self.database.insert_audit_log(
                id=entry.id,
                actor_id=entry.actor_id,
                action=entry.action,
                target_type=entry.target_type,
                target_id=entry.target_id,
                details=entry.details,
                created_at=entry.created_at,
            )
        except Exception:
            logger.error(
                "admin_audit_write_failed",
                extra={
                    "actorId": actor_id,
                    "action": action,
                    "targetId": target_id,
                    "targetType": target_type,
                },
            )

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
