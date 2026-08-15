from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.errors import AppError
from app.generation_log_service import GenerationLogService
from app.providers import PollResult, ProviderRegistry
from app.quota_service import QuotaService
from app.repository import ProjectRepository
from app.schemas import PageInfo, ProjectCreate, ProjectPage, ProjectResponse, WebhookResponse
from app.storage import StorageBackend, assert_owns_path
from app.thumbnails import ThumbnailGenerator
from app.transitions import IN_FLIGHT, assert_transition, is_retryable

FAILURE_MESSAGES = {
    "content_policy": "The prompt or image could not be used. Try different content.",
    "invalid_input": "The video request is not supported. Check the input and try again.",
    "quota": "The video service quota is currently unavailable.",
    "timeout": "Video generation took too long. Please retry later.",
    "provider_error": "The video service had a problem. Please try again.",
    "unknown": "Video generation failed. Please try again.",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class ProjectService:
    def __init__(
        self,
        database: ProjectRepository,
        providers: ProviderRegistry,
        settings: Settings,
        storage: StorageBackend,
        quota: QuotaService,
        generation_log: GenerationLogService,
        thumbnails: ThumbnailGenerator,
    ) -> None:
        self.thumbnails = thumbnails
        self.database = database
        self.providers = providers
        self.settings = settings
        self.storage = storage
        self.quota = quota
        self.generation_log = generation_log

    def create(
        self,
        owner_id: str,
        request: ProjectCreate,
        idempotency_key: str | None,
        base_url: str,
    ) -> ProjectResponse:
        if idempotency_key:
            existing = self.database.find_by_idempotency(owner_id, idempotency_key)
            if existing:
                return self.to_response(existing, base_url)

        # A path is only usable by the person who uploaded it; otherwise a user
        # could attach someone else's image to their own project.
        if request.image_path:
            assert_owns_path(owner_id, request.image_path)

        provider = self.providers.get(request.provider)

        # Cost weighting: real providers or longer videos consume 2 quota units
        has_long_duration = (
            request.options is not None
            and request.options.duration_seconds is not None
            and request.options.duration_seconds > 5
        )
        cost = 2 if (has_long_duration or provider.name in ("real", "wan21")) else 1

        # Before the provider call, never after: checking afterwards is
        # accounting, not control (ADR-007).
        self.quota.assert_available(owner_id, cost=cost)

        now = utc_now()
        prompt = request.prompt
        title = request.title or self._derive_title(prompt)
        values: dict[str, Any] = {
            "id": str(uuid4()),
            "owner_id": owner_id,
            "title": title,
            "prompt": prompt,
            "image_path": request.image_path,
            "provider": provider.name,
            "status": "pending",
            "provider_job_id": None,
            "error_code": None,
            "error_message": None,
            "duration_seconds": request.options.duration_seconds,
            "aspect_ratio": request.options.aspect_ratio,
            "video_path": None,
            "thumbnail_path": None,
            "poll_count": 0,
            "attempt_count": 0,
            "idempotency_key": idempotency_key,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }
        row, created = self.database.create_project(values)
        if not created:
            return self.to_response(row, base_url)

        try:
            submitted = provider.submit(prompt=prompt, image_path=request.image_path)
            self.generation_log.record(
                project_id=row["id"],
                provider=provider.name,
                event="submit",
                request_id=submitted.job_id,
                request={"prompt": prompt, "imagePath": request.image_path},
            )
            updated = self.database.update_project(
                row["id"],
                owner_id,
                {
                    "provider_job_id": submitted.job_id,
                    # A submission is the unit a retry budget counts (FR-2.11).
                    "attempt_count": 1,
                    # The attempt clock starts when the provider accepts it,
                    # not when the row was created.
                    "started_at": utc_now(),
                    "updated_at": utc_now(),
                },
                expected_status="pending",
            )
            return self.to_response(updated or row, base_url)
        except Exception as exc:
            self.generation_log.record(
                project_id=row["id"],
                provider=provider.name,
                event="error",
                request={"prompt": prompt, "imagePath": request.image_path},
                response={"message": str(exc)},
            )
            failed = self.database.update_project(
                row["id"],
                owner_id,
                {
                    "status": "failed",
                    "error_code": "provider_error",
                    "error_message": FAILURE_MESSAGES["provider_error"],
                    "updated_at": utc_now(),
                    "completed_at": utc_now(),
                },
                expected_status="pending",
            )
            if failed is None:  # pragma: no cover - defensive concurrent update guard
                raise RuntimeError("Could not persist provider submission failure") from exc
            return self.to_response(failed, base_url)

    def get(self, owner_id: str, project_id: str, base_url: str) -> ProjectResponse:
        row = self._owned(owner_id, project_id)
        row = self._advance(row, owner_id)
        return self.to_response(row, base_url)

    def list(
        self,
        owner_id: str,
        *,
        limit: int,
        status: str | None,
        cursor: str | None,
        base_url: str,
    ) -> ProjectPage:
        try:
            rows, next_cursor = self.database.list_projects(
                owner_id,
                limit=limit,
                status=status,
                cursor=cursor,
            )
        except ValueError as exc:
            raise AppError(
                400,
                "VALIDATION_ERROR",
                "The pagination cursor is invalid.",
                [{"field": "query.cursor", "issue": "invalid_cursor"}],
            ) from exc
        return ProjectPage(
            items=[self.to_response(row, base_url) for row in rows],
            page=PageInfo(nextCursor=next_cursor, hasMore=next_cursor is not None),
        )

    def delete(self, owner_id: str, project_id: str) -> None:
        row = self._owned(owner_id, project_id)
        # Deleting mid-generation would orphan a provider job that still bills
        # us and would later write to a row the user believes is gone.
        if row["status"] == "generating":
            raise AppError(409, "CONFLICT", "A generating project cannot be deleted.")
        if not self.database.soft_delete_project(project_id, owner_id, utc_now()):
            raise AppError(404, "NOT_FOUND", "Project not found.")

        # Media is removed eagerly even though the row is only soft-deleted:
        # storage costs money and the user asked for it to be gone.
        self.storage.remove_objects(row["image_path"], row["video_path"])

    def retry(self, owner_id: str, project_id: str, base_url: str) -> ProjectResponse:
        row = self._owned(owner_id, project_id)
        assert_transition(row["status"], "pending")

        # A request the provider rejected on its merits will be rejected again,
        # so retrying only burns the user's allowance.
        if not is_retryable(row["error_code"]):
            raise AppError(
                409,
                "CONFLICT",
                "This generation cannot be retried because the request itself was rejected.",
            )

        attempts = int(row["attempt_count"] or 0)
        if attempts >= self.settings.max_generation_attempts:
            raise AppError(409, "CONFLICT", "This generation has been retried too many times.")

        # A retry is a real provider call, so it costs an allowance (ADR-007).
        self.quota.assert_available(owner_id)

        provider = self.providers.get(row["provider"])
        submitted = provider.submit(prompt=row["prompt"], image_path=row["image_path"])
        now = utc_now()
        updated = self.database.update_project(
            project_id,
            owner_id,
            {
                "status": "pending",
                "provider_job_id": submitted.job_id,
                "error_code": None,
                "error_message": None,
                "video_path": None,
                "thumbnail_path": None,
                "poll_count": 0,
                "attempt_count": attempts + 1,
                # A fresh attempt gets a fresh timeout budget. Without this a
                # project created long ago would time out the instant it was
                # retried, which defeats the point of retrying.
                "started_at": now,
                "updated_at": now,
                "completed_at": None,
            },
            expected_status="failed",
        )
        if updated is None:
            raise AppError(409, "CONFLICT", "Project state changed before retry.")
        return self.to_response(updated, base_url)

    def advance(self, row: dict[str, Any]) -> dict[str, Any]:
        """Move a project one step, for callers that already hold the row.

        The poller uses this; reads reach the same code through `get`, so both
        paths share one state machine rather than drifting apart.
        """
        return self._advance(row, row["owner_id"])

    def _advance(self, row: dict[str, Any], owner_id: str) -> dict[str, Any]:
        # Checked before anything else, so a provider that accepted a job and
        # then went quiet cannot hold a project in flight forever. Without
        # this the poller re-polls a dead job on every pass, indefinitely.
        if row["status"] in IN_FLIGHT and self._timed_out(row):
            return self._mark_failed(row, owner_id, "timeout")

        if row["status"] == "pending":
            if not row["provider_job_id"]:
                return self._mark_failed(row, owner_id, "provider_error")
            updated = self.database.update_project(
                row["id"],
                owner_id,
                {"status": "generating", "updated_at": utc_now()},
                expected_status="pending",
            )
            return updated or self._owned(owner_id, row["id"])

        if row["status"] != "generating":
            return row

        provider = self.providers.get(row["provider"])
        poll_count = int(row["poll_count"]) + 1
        result = provider.poll(
            job_id=row["provider_job_id"],
            prompt=row["prompt"],
            poll_count=poll_count,
        )
        self.generation_log.record(
            project_id=row["id"],
            provider=provider.name,
            event="poll",
            request_id=row["provider_job_id"],
            response={"status": result.status, "failure": result.failure},
        )
        return self._apply_poll(row, owner_id, poll_count, result)

    def _apply_poll(
        self,
        row: dict[str, Any],
        owner_id: str,
        poll_count: int,
        result: PollResult,
    ) -> dict[str, Any]:
        now = utc_now()
        if result.status == "running":
            updated = self.database.update_project(
                row["id"],
                owner_id,
                {"poll_count": poll_count, "updated_at": now},
                expected_status="generating",
            )
        elif result.status == "succeeded":
            try:
                stored_path = self._rehost(row, owner_id, result.video_path)
                thumbnail_path = self._thumbnail(row, owner_id, stored_path)
            except AppError:
                # Re-hosting failure fails the project rather than completing
                # it: a completed project whose video is a provider URL is a
                # broken link the moment that URL expires.
                return self._mark_failed(row, owner_id, "provider_error", poll_count)

            updated = self.database.update_project(
                row["id"],
                owner_id,
                {
                    "status": "completed",
                    "video_path": stored_path,
                    "thumbnail_path": thumbnail_path,
                    "duration_seconds": result.duration_seconds,
                    "poll_count": poll_count,
                    "updated_at": now,
                    "completed_at": now,
                },
                expected_status="generating",
            )
        else:
            return self._mark_failed(row, owner_id, result.failure or "unknown", poll_count)
        return updated or self._owned(owner_id, row["id"])

    def _rehost(self, row: dict[str, Any], owner_id: str, source: str | None) -> str | None:
        """Copy a finished result into our own storage before completing.

        Provider URLs expire, so persisting one guarantees a broken link within
        days (P3-8). The bytes become ours first; only then is the project
        completed.
        """
        if not source:
            return None
        stored = self.storage.store_video(owner_id, row["id"], source)
        self.generation_log.record(
            project_id=row["id"],
            provider=row["provider"],
            event="download",
            response={"storedPath": stored},
        )
        return stored

    def _timed_out(self, row: dict[str, Any]) -> bool:
        """Has the current attempt been in flight too long?

        Measured from `started_at`, which is set on submit and reset on every
        retry, so each attempt gets the full budget. Rows written before that
        column existed have none, and fall back to `created_at` rather than
        being read as having started at the epoch and failed on sight.
        """
        started = _parse_timestamp(row.get("started_at")) or _parse_timestamp(row.get("created_at"))
        if started is None:
            return False
        age = (datetime.now(UTC) - started).total_seconds()
        return age > self.settings.generation_timeout_seconds

    def _thumbnail(
        self,
        row: dict[str, Any],
        owner_id: str,
        stored_path: str | None,
    ) -> str | None:
        """Best effort. A missing thumbnail must not fail a finished video."""
        if not stored_path:
            return None

        source = self.storage.local_video_path(stored_path)
        if source is None or not source.exists():
            return None

        target_path = self.storage.store_thumbnail_path(owner_id, row["id"])
        if getattr(self.storage, "name", "") == "supabase":
            temp_target = source.parent / f"thumb_{row['id']}.jpg"
            try:
                if not self.thumbnails.extract(source, temp_target):
                    return None
                store_fn = getattr(self.storage, "store_thumbnail", None)
                if store_fn is not None:
                    res = store_fn(owner_id, row["id"], temp_target.read_bytes())
                    return res if res else None
                return None
            finally:
                temp_target.unlink(missing_ok=True)
        else:
            target = source.parent / "thumbnail.jpg"
            return target_path if self.thumbnails.extract(source, target) else None

    def _mark_failed(
        self,
        row: dict[str, Any],
        owner_id: str,
        failure: str,
        poll_count: int | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        values: dict[str, Any] = {
            "status": "failed",
            "error_code": failure,
            "error_message": FAILURE_MESSAGES.get(failure, FAILURE_MESSAGES["unknown"]),
            "updated_at": now,
            "completed_at": now,
        }
        if poll_count is not None:
            values["poll_count"] = poll_count
        updated = self.database.update_project(
            row["id"],
            owner_id,
            values,
            expected_status=row["status"],
        )
        return updated or self._owned(owner_id, row["id"])

    def _owned(self, owner_id: str, project_id: str) -> dict[str, Any]:
        row = self.database.get_project(project_id, owner_id)
        if row is None:
            raise AppError(404, "NOT_FOUND", "Project not found.")
        return row

    @staticmethod
    def _derive_title(prompt: str | None) -> str:
        if not prompt:
            return "Image video"
        return prompt[:60].strip() or "Untitled video"

    def to_response(self, row: dict[str, Any], base_url: str) -> ProjectResponse:
        def media_url(path: str | None, *, video: bool = True) -> str | None:
            # Storage owns URL shape. On Supabase these are short-lived signed
            # URLs minted per response and never persisted, because a stored
            # URL is a guaranteed-stale link once it expires.
            return self.storage.read_url(path, base_url, video=video)

        return ProjectResponse(
            id=row["id"],
            title=row["title"],
            prompt=row["prompt"],
            imageUrl=media_url(row["image_path"], video=False),
            videoUrl=media_url(row["video_path"]),
            thumbnailUrl=media_url(row["thumbnail_path"]),
            status=row["status"],
            provider=row["provider"],
            errorMessage=row["error_message"],
            durationSeconds=row["duration_seconds"],
            aspectRatio=row["aspect_ratio"],
            createdAt=row["created_at"],
            updatedAt=row["updated_at"],
            completedAt=row["completed_at"],
        )

    def process_webhook(
        self,
        provider_name: str,
        headers: dict[str, str],
        body: bytes,
        base_url: str,
    ) -> WebhookResponse:
        provider = self.providers.get(provider_name)
        payload = provider.verify_webhook(headers=headers, body=body)

        job_id = payload.get("job_id") or payload.get("provider_job_id")
        project_id = payload.get("project_id") or payload.get("projectId")

        row = None
        if project_id:
            row = self.database.get_project_by_id(project_id)
        elif job_id:
            row = self.database.find_by_provider_job_id(job_id)

        if not row:
            raise AppError(404, "NOT_FOUND", "Project for webhook was not found.")

        owner_id = row["owner_id"]
        status_event = payload.get("status")
        now = utc_now()

        safe_headers = {
            k: v for k, v in headers.items() if not k.lower().startswith("authorization")
        }
        self.generation_log.record(
            project_id=row["id"],
            provider=provider_name,
            event="webhook",
            request_id=job_id,
            request={"headers": safe_headers},
            response=payload,
        )

        if status_event in ("succeeded", "completed"):
            video_url = payload.get("video_path") or payload.get("video_url")
            try:
                stored_path = self._rehost(row, owner_id, video_url)
                thumbnail_path = self._thumbnail(row, owner_id, stored_path)
            except AppError:
                self._mark_failed(row, owner_id, "provider_error")
                return WebhookResponse(received=True, projectId=row["id"], status="failed")

            duration = payload.get("duration_seconds") or row.get("duration_seconds") or 5
            self.database.update_project(
                row["id"],
                owner_id,
                {
                    "status": "completed",
                    "video_path": stored_path,
                    "thumbnail_path": thumbnail_path,
                    "duration_seconds": duration,
                    "updated_at": now,
                    "completed_at": now,
                },
            )
            return WebhookResponse(received=True, projectId=row["id"], status="completed")
        elif status_event == "failed":
            failure = payload.get("failure") or payload.get("error_code") or "provider_error"
            self._mark_failed(row, owner_id, failure)
            return WebhookResponse(received=True, projectId=row["id"], status="failed")

        return WebhookResponse(received=True, projectId=row["id"], status=row["status"])
