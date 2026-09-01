from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.credit_service import CreditService
from app.errors import AppError
from app.generation_log_service import GenerationLogService
from app.providers import PollResult, ProviderRegistry
from app.quota_service import QuotaService
from app.repository import ProjectRepository
from app.schemas import (
    PageInfo,
    ProjectCancelResponse,
    ProjectCreate,
    ProjectPage,
    ProjectResponse,
    WebhookResponse,
)
from app.storage import StorageBackend, assert_owns_path
from app.thumbnails import ThumbnailGenerator
from app.transitions import IN_FLIGHT, assert_transition, is_retryable

logger = logging.getLogger("cretona.projects")

FAILURE_MESSAGES = {
    "content_policy": "The prompt or image could not be used. Try different content.",
    "invalid_input": "The video request is not supported. Check the input and try again.",
    "quota": "The video service quota is currently unavailable.",
    "timeout": "Video generation took too long. Please retry later.",
    "provider_error": "The video service had a problem. Please try again.",
    "cancelled": "Generation was cancelled by the user.",
    "unknown": "Video generation failed. Please try again.",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# Providers whose output costs enough to charge double (B-14).
WEIGHTED_PROVIDERS = frozenset({"real", "wan21", "cloud", "local"})


STYLE_PRESET_DIRECTIVES: dict[str, str] = {
    "anime": (
        "in vibrant anime aesthetic, Studio Ghibli style lighting, "
        "rich hand-drawn details, expressive atmosphere"
    ),
    "cyberpunk": (
        "in cyberpunk 2077 aesthetic, glowing neon lights, futuristic cityscape, "
        "rainy volumetric reflections, dark atmosphere"
    ),
    "3d_pixar": (
        "in 3D animation Pixar Disney style, soft subsurface scattering, "
        "cute character rendering, vibrant warm lighting, octane render"
    ),
    "vintage_film": (
        "in vintage 35mm film aesthetic, Kodak Portra grain, "
        "warm analog color grading, soft vintage lens blur"
    ),
    "photorealistic": (
        "in 8k hyperrealistic cinematic look, ultra detailed textures, "
        "IMAX camera quality, natural depth of field"
    ),
}

CAMERA_MOTION_DIRECTIVES: dict[str, str] = {
    "pan_left": "camera smoothly panning left",
    "pan_right": "camera smoothly panning right",
    "zoom_in": "slow dramatic camera zoom in",
    "zoom_out": "smooth camera zoom out revealing the wider scene",
    "dolly_zoom": "dramatic dolly zoom vertigo effect",
    "orbit": "camera smoothly orbiting around the subject 360 degrees",
}


def compose_enhanced_prompt(
    prompt: str | None,
    style_preset: str | None = None,
    camera_motion: str | None = None,
) -> str | None:
    if not prompt:
        return None
    parts = [prompt.strip()]
    if style_preset and style_preset in STYLE_PRESET_DIRECTIVES:
        parts.append(STYLE_PRESET_DIRECTIVES[style_preset])
    if camera_motion and camera_motion in CAMERA_MOTION_DIRECTIVES:
        parts.append(CAMERA_MOTION_DIRECTIVES[camera_motion])
    return ", ".join(parts)[:1000]


def generation_mode(prompt: str | None, image_path: str | None) -> str:
    """What the caller actually supplied.

    Derived here rather than accepted from the request: a client-declared mode
    could disagree with the fields it sent, and then two parts of the system
    would have different ideas about what the user asked for.
    """
    has_prompt = bool(prompt and prompt.strip())
    has_image = bool(image_path)
    if has_prompt and has_image:
        return "text_image"
    if has_image:
        return "image"
    return "text"


def quota_cost(provider_name: str, duration_seconds: int | None) -> int:
    """Weighted cost of one submission.

    Shared by create and retry so both charge what the row will later be
    counted at. The SQL in count_quota_usage applies the same rule.
    """
    if provider_name in WEIGHTED_PROVIDERS:
        return 2
    if duration_seconds is not None and duration_seconds > 5:
        return 2
    return 1


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
        credits: CreditService,
        events: Any = None,
    ) -> None:
        self.thumbnails = thumbnails
        self.database = database
        self.providers = providers
        self.settings = settings
        self.storage = storage
        self.quota = quota
        self.generation_log = generation_log
        self.credits = credits
        self.events = events

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

        mode = generation_mode(request.prompt, request.image_path)
        if mode != "text" and not getattr(provider, "supports_image", False):
            # Never silently fall back to text-only (API_CONTRACT.md §5). A
            # user who supplied an image and received a video that ignores it
            # has been misled, and would have no way to tell.
            raise AppError(
                502,
                "PROVIDER_ERROR",
                "Image-to-video is not available yet. "
                "Remove the image to generate from the prompt alone.",
            )

        duration = request.options.duration_seconds if request.options is not None else None
        self._assert_duration_supported(provider, duration)

        # Before the provider call, never after: checking afterwards is
        # accounting, not control (ADR-007).
        self.quota.assert_available(owner_id, cost=quota_cost(provider.name, duration))

        # The id is generated here rather than inline below so the charge can
        # reference the project it pays for. Reserve before submitting, so a
        # user with one credit cannot start ten jobs (API_CONTRACT.md §10.1).
        project_id = str(uuid4())
        self._charge_for_generation(owner_id, project_id)

        now = utc_now()
        effective_prompt = compose_enhanced_prompt(
            request.prompt,
            request.options.style_preset if request.options else None,
            request.options.camera_motion if request.options else None,
        )
        prompt = effective_prompt or request.prompt
        title = request.title or self._derive_title(prompt)
        values: dict[str, Any] = {
            "id": project_id,
            "owner_id": owner_id,
            "title": title,
            "prompt": prompt,
            "image_path": request.image_path,
            "provider": request.provider or provider.name,
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
            "progress_percent": 0,
            "step_message": "Queued in generation pipeline",
            "idempotency_key": idempotency_key,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }
        try:
            row, created = self.database.create_project(values)
        except Exception:
            # Nothing was generated and nothing is queued, so the reservation
            # has to come back. Without this the credits would be spent on a
            # project that does not exist.
            self._refund_generation(owner_id, project_id, "Project could not be created")
            raise

        if not created:
            # An idempotency race: another request already created this project
            # under the same key, and this one's charge paid for nothing.
            self._refund_generation(owner_id, project_id, "Duplicate submission")
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
            # The user got no video, so they keep their credits. The brief
            # allows either not charging or refunding; this is the refund half.
            self._refund_generation(owner_id, row["id"], "Generation failed to start")
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

        provider = self.providers.get(row["provider"])
        self._assert_duration_supported(provider, row["duration_seconds"])

        # A retry is a real provider call, so it costs an allowance (ADR-007) —
        # and it is charged at the same weight the row will be counted at, or a
        # weighted retry could take a user past the limit.
        self.quota.assert_available(
            owner_id,
            cost=quota_cost(row["provider"], row["duration_seconds"]),
        )

        # A retry is a real generation, so it is charged again -- the same
        # reasoning ADR-007 applies to the quota allowance. The key includes the
        # attempt number, so each attempt is its own charge rather than being
        # swallowed as a replay of the first.
        self._charge_for_generation(owner_id, project_id, attempt=attempts + 1, note="Retry")

        try:
            submitted = provider.submit(prompt=row["prompt"], image_path=row["image_path"])
        except Exception:
            self._refund_generation(owner_id, project_id, "Retry failed to start")
            raise
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
        provider = self.providers.get(row["provider"])
        if getattr(provider, "external", False):
            # The external worker is the sole owner of its state machine. A
            # read must not reset worker progress or apply the ten-minute
            # in-process timeout to a proven ~49-minute Kaggle generation.
            return row

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
                {
                    "status": "generating",
                    "progress_percent": 15,
                    "step_message": "Initializing video generation pipeline...",
                    "updated_at": utc_now(),
                },
                expected_status="pending",
            )
            return updated or self._owned(owner_id, row["id"])

        if row["status"] != "generating":
            return row

        poll_count = int(row["poll_count"]) + 1
        result = provider.poll(
            job_id=row["provider_job_id"],
            prompt=row["prompt"],
            poll_count=poll_count,
            # The reference image the account uploaded. Providers that cannot
            # use it ignore it; the ones that render a frame pan across it
            # instead of a generated still.
            image_path=row["image_path"],
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
                {
                    "poll_count": poll_count,
                    "progress_percent": result.progress_percent,
                    "step_message": result.step_message,
                    "updated_at": now,
                },
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
                    "progress_percent": 100,
                    "step_message": result.step_message or "Video rendering complete",
                    "updated_at": now,
                    "completed_at": now,
                },
                expected_status="generating",
            )
        else:
            return self._mark_failed(row, owner_id, result.failure or "unknown", poll_count)
        return updated or self._owned(owner_id, row["id"])

    def cancel(self, owner_id: str, project_id: str) -> ProjectCancelResponse:
        row = self._owned(owner_id, project_id)
        if row["status"] not in IN_FLIGHT:
            raise AppError(409, "CONFLICT", f"Cannot cancel project with status '{row['status']}'.")

        now = utc_now()
        updated = self.database.update_project(
            project_id,
            owner_id,
            {
                "status": "failed",
                "error_code": "cancelled",
                "error_message": FAILURE_MESSAGES["cancelled"],
                "progress_percent": 0,
                "step_message": "Cancelled by user",
                "updated_at": now,
                "completed_at": now,
            },
            expected_status=row["status"],
        )
        if updated is None:
            raise AppError(409, "CONFLICT", "Project state changed before cancellation.")

        self._refund_generation(owner_id, project_id, "Cancelled by user")

        self.generation_log.record(
            project_id=project_id,
            provider=row["provider"],
            event="error",
            request={"action": "cancel", "userId": owner_id},
            response={"message": "Generation cancelled by user"},
        )
        return ProjectCancelResponse(
            cancelled=True,
            projectId=project_id,
            quotaRefunded=True,
        )

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

        # Every terminal failure funnels through here -- timeout, provider
        # error, webhook failure -- so this is the one place a refund has to
        # live for all of them. `refund_for` is idempotent and returns None
        # when there is nothing to give back, so calling it on a path that was
        # never charged costs a lookup and changes nothing.
        self._refund_generation(owner_id, row["id"], FAILURE_MESSAGES.get(failure, failure))

        updated = self.database.update_project(
            row["id"],
            owner_id,
            values,
            expected_status=row["status"],
        )
        return updated or self._owned(owner_id, row["id"])

    def _charge_for_generation(
        self,
        owner_id: str,
        project_id: str,
        *,
        attempt: int = 1,
        note: str | None = None,
    ) -> int:
        """Reserve the cost of one generation. Raises 402 if it will not cover.

        The price is resolved here rather than passed in, because the discount
        that applies is the one running at this instant -- a client that
        rendered "1 credit" a minute ago does not get to decide what it pays.

        The idempotency key is derived from the project and the attempt, so the
        same submission can never be charged twice while a genuine retry still
        is.
        """
        if self.database.get_user(owner_id) is None:
            # No profile row, so there is no balance to charge against.
            #
            # This is unreachable in any deployed profile: `_resolved_account`
            # returns 401 before a request gets this far without a row, and the
            # Supabase signup trigger creates one. It is reachable only in
            # `auth_mode=dev`, which takes an identity from a header and
            # deliberately never provisions anything (see the note on
            # test_missing_profile_is_not_found).
            #
            # Skipping the charge there keeps dev mode working as documented
            # without weakening billing anywhere it actually applies.
            return 0

        base = self.credits.generation_cost()
        discount = self._active_discount_percent()
        cost = CreditService.effective_cost(base, discount)
        if discount and not note:
            # The ledger has to explain why this row is 1 and yesterday's was 2.
            note = f"-{discount}% event"
        self.credits.charge(
            owner_id,
            cost,
            reason="generation",
            ref_type="project",
            ref_id=project_id,
            note=note,
            idempotency_key=f"generation:{project_id}:{attempt}",
        )
        return cost

    def _refund_generation(self, owner_id: str, project_id: str, note: str) -> None:
        """Give back what this project was charged, if anything.

        Deliberately swallows its own failures. A refund that raises would turn
        a failed generation into a 500 and leave the project stuck in flight,
        which is worse for the user than a refund that has to be chased. The
        drift query in `ledger_drift()` is how that would be found.
        """
        try:
            self.credits.refund_for(owner_id, ref_type="project", ref_id=project_id, note=note)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Refund failed for project %s", project_id)

    def _active_discount_percent(self) -> int | None:
        """The discount running right now, or None.

        Resolved at charge time, not read from the request. A client that
        rendered "1 credit" a minute ago does not get to decide what it pays,
        and a discount that ended in between charges full price
        (API_CONTRACT.md §10.2).

        A failure here must not stop a generation: a broken campaign should
        cost the user full price, not the ability to generate at all.
        """
        if self.events is None:
            return None
        try:
            return self.events.discount_percent()
        except Exception:  # pragma: no cover - defensive
            logger.exception("Could not resolve the active discount")
            return None

    @staticmethod
    def _assert_duration_supported(provider: Any, duration: int | None) -> None:
        max_duration = getattr(provider, "max_duration_seconds", None)
        if duration is not None and max_duration is not None and duration > max_duration:
            raise AppError(
                400,
                "VALIDATION_ERROR",
                f"{provider.name} currently supports videos up to {max_duration} seconds.",
                [{"field": "body.options.durationSeconds", "issue": "provider_limit"}],
            )

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

        progress = int(row.get("progress_percent") or (100 if row["status"] == "completed" else 0))
        return ProjectResponse(
            id=row["id"],
            title=row["title"],
            prompt=row["prompt"],
            # Recomputed from the stored inputs rather than persisted: there is
            # no column that could drift out of step with them.
            mode=generation_mode(row.get("prompt"), row.get("image_path")),
            imageUrl=media_url(row.get("image_path"), video=False),
            videoUrl=media_url(row.get("video_path")),
            # video=False on purpose: `SupabaseStorage.store_thumbnail` writes
            # into the uploads bucket, so signing this against `videos` finds
            # nothing and returns None -- which the app renders as
            # "Preview unavailable" even when the thumbnail exists.
            thumbnailUrl=media_url(row.get("thumbnail_path"), video=False),
            status=row["status"],
            provider=row["provider"],
            errorMessage=row.get("error_message"),
            progressPercent=progress,
            stepMessage=row.get("step_message"),
            durationSeconds=row.get("duration_seconds"),
            aspectRatio=row.get("aspect_ratio") or "16:9",
            createdAt=row["created_at"],
            updatedAt=row["updated_at"],
            completedAt=row.get("completed_at"),
        )

    def process_webhook(
        self,
        provider_name: str,
        headers: dict[str, str],
        body: bytes,
        base_url: str,
    ) -> WebhookResponse:
        provider = self.providers.get(provider_name)
        payload = provider.verify_webhook(
            headers=headers,
            body=body,
            secret=self.settings.webhook_secret.get_secret_value(),
            tolerance_seconds=self.settings.webhook_tolerance_seconds,
        )

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
