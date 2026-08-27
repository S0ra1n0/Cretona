from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ProjectStatus(StrEnum):
    pending = "pending"
    generating = "generating"
    completed = "completed"
    failed = "failed"


AspectRatio = Literal["16:9", "9:16", "1:1"]
StylePreset = Literal["anime", "cyberpunk", "3d_pixar", "vintage_film", "photorealistic"]
CameraMotion = Literal["pan_left", "pan_right", "zoom_in", "zoom_out", "dolly_zoom", "orbit"]

# Stored lowercase; the app capitalises for display. "other" is deliberately
# last-resort rather than a catch-all label the account never chose.
GENDERS = frozenset({"male", "female", "other"})


class GenerationOptions(ApiModel):
    duration_seconds: Annotated[int, Field(alias="durationSeconds", ge=2, le=10)] = 5
    aspect_ratio: AspectRatio = Field(default="16:9", alias="aspectRatio")
    style_preset: StylePreset | None = Field(default=None, alias="stylePreset")
    camera_motion: CameraMotion | None = Field(default=None, alias="cameraMotion")


class ProjectCreate(ApiModel):
    title: Annotated[str | None, Field(default=None, max_length=120)]
    prompt: Annotated[str | None, Field(default=None, max_length=1000)]
    image_path: str | None = Field(default=None, alias="imagePath")
    provider: str | None = None
    options: GenerationOptions = Field(default_factory=GenerationOptions)

    @model_validator(mode="after")
    def require_input(self) -> ProjectCreate:
        if not (self.prompt and self.prompt.strip()) and not self.image_path:
            raise ValueError("At least one of prompt or imagePath is required.")
        if self.prompt is not None:
            self.prompt = self.prompt.strip() or None
        return self


class ProjectResponse(ApiModel):
    id: str
    title: str
    prompt: str | None
    image_url: str | None = Field(alias="imageUrl")
    video_url: str | None = Field(alias="videoUrl")
    thumbnail_url: str | None = Field(alias="thumbnailUrl")
    status: ProjectStatus
    provider: str
    error_message: str | None = Field(alias="errorMessage")
    progress_percent: int = Field(default=0, alias="progressPercent")
    step_message: str | None = Field(default=None, alias="stepMessage")
    duration_seconds: int | None = Field(alias="durationSeconds")
    aspect_ratio: AspectRatio = Field(alias="aspectRatio")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    completed_at: datetime | None = Field(alias="completedAt")


class ProjectCancelResponse(ApiModel):
    cancelled: bool
    project_id: str = Field(alias="projectId")
    quota_refunded: bool = Field(alias="quotaRefunded")


class PageInfo(ApiModel):
    next_cursor: str | None = Field(alias="nextCursor")
    has_more: bool = Field(alias="hasMore")


class ProjectPage(ApiModel):
    items: list[ProjectResponse]
    page: PageInfo


class PromptEnhanceRequest(ApiModel):
    prompt: Annotated[str, Field(min_length=1, max_length=1000)]
    aspect_ratio: AspectRatio = Field(default="16:9", alias="aspectRatio")


class PromptEnhanceResponse(ApiModel):
    original_prompt: str = Field(alias="originalPrompt")
    enhanced_prompt: str = Field(alias="enhancedPrompt")
    provider: str
    used_fallback: bool = Field(alias="usedFallback")


RoleName = Literal["user", "admin"]


class Quota(ApiModel):
    limit: int
    used: int
    remaining: int
    resets_at: str = Field(alias="resetsAt")


class MeResponse(ApiModel):
    id: str
    email: str | None
    username: str | None
    # Signed per response and never persisted, for the same reason videoUrl is:
    # a stored signed URL is a broken image once it expires.
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    # Optional profile details; null until the account chooses one.
    gender: str | None = None
    birthday: str | None = None
    role: str
    is_disabled: bool = Field(alias="isDisabled")
    created_at: str = Field(alias="createdAt")
    quota: Quota


class MeUpdate(ApiModel):
    # Explicitly nullable: sending null releases the name, which is the only
    # way to give one up once taken.
    username: Annotated[
        str | None,
        Field(min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_]+$"),
    ]
    # Storage object key from POST /uploads, not a URL. Absent means "leave the
    # avatar as it is"; explicit null means "remove it".
    avatar_path: str | None = Field(default=None, alias="avatarPath")
    # Optional details. Absent means "leave as is"; empty string means "clear".
    # Empty string rather than null because the app serialises with
    # explicitNulls=false, which drops null fields from the body entirely --
    # a null would therefore be indistinguishable from "not sent" and no
    # value could ever be taken back once set.
    gender: str | None = None
    birthday: str | None = None

    @field_validator("gender", mode="before")
    @classmethod
    def _normalise_gender(cls, value: Any) -> Any:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered not in GENDERS:
                raise ValueError(f"gender must be one of {', '.join(sorted(GENDERS))}")
            return lowered
        return value

    @field_validator("birthday", mode="before")
    @classmethod
    def _normalise_birthday(cls, value: Any) -> Any:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, str):
            candidate = value.strip()
            try:
                parsed = date.fromisoformat(candidate)
            except ValueError as exc:
                raise ValueError("birthday must be an ISO date (YYYY-MM-DD)") from exc
            # A birthday in the future is a typo, not a preference. Rejecting
            # it here keeps the stored value meaningful for any later
            # age-derived logic.
            if parsed > date.today():
                raise ValueError("birthday cannot be in the future")
            return parsed.isoformat()
        return value


class AdminUser(ApiModel):
    id: str
    email: str | None
    username: str | None
    role: str
    is_disabled: bool = Field(alias="isDisabled")
    project_count: int = Field(alias="projectCount")
    created_at: str = Field(alias="createdAt")


class AdminUserPage(ApiModel):
    items: list[AdminUser]
    page: PageInfo


class AdminUserUpdate(ApiModel):
    role: RoleName | None = None
    is_disabled: bool | None = Field(default=None, alias="isDisabled")

    @model_validator(mode="after")
    def require_a_change(self) -> AdminUserUpdate:
        if self.role is None and self.is_disabled is None:
            raise ValueError("Provide role, isDisabled, or both.")
        return self


class StatsTotals(ApiModel):
    users: int
    active_users: int = Field(alias="activeUsers")
    projects: int


class DailyStat(ApiModel):
    date: str
    created: int
    completed: int
    failed: int


class StatsResponse(ApiModel):
    totals: StatsTotals
    projects_by_status: dict[str, int] = Field(alias="projectsByStatus")
    projects_by_provider: dict[str, int] = Field(alias="projectsByProvider")
    failure_rate: float = Field(alias="failureRate")
    daily: list[DailyStat]


class UploadSignRequest(ApiModel):
    content_type: str = Field(alias="contentType")
    size_bytes: Annotated[int, Field(alias="sizeBytes", gt=0)]


class UploadSignResponse(ApiModel):
    upload_url: str = Field(alias="uploadUrl")
    storage_path: str = Field(alias="storagePath")
    token: str
    expires_at: str = Field(alias="expiresAt")


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    version: str


class AdminMetricsResponse(ApiModel):
    uptime_seconds: float = Field(alias="uptimeSeconds")
    active_jobs: int = Field(alias="activeJobs")
    completed_jobs: int = Field(alias="completedJobs")
    failed_jobs: int = Field(alias="failedJobs")
    memory_rss_mb: float = Field(alias="memoryRssMb")
    database_backend: str = Field(alias="databaseBackend")
    database_status: str = Field(alias="databaseStatus")
    storage_backend: str = Field(alias="storageBackend")


class AdminLogItem(ApiModel):
    id: str | int | None = None
    project_id: str = Field(alias="projectId")
    provider: str
    request_id: str | None = Field(default=None, alias="requestId")
    event: str
    request: Any = None
    response: Any = None
    http_status: int | None = Field(default=None, alias="httpStatus")
    created_at: str = Field(alias="createdAt")


class AdminLogList(ApiModel):
    items: list[AdminLogItem]


class BackfillResponse(ApiModel):
    backfilled: int
    processed: int


class AdminAuditLog(ApiModel):
    id: str
    actor_id: str = Field(alias="actorId")
    action: str
    target_type: str = Field(alias="targetType")
    target_id: str | None = Field(default=None, alias="targetId")
    details: Any = None
    created_at: str = Field(alias="createdAt")


class AdminAuditLogPage(ApiModel):
    items: list[AdminAuditLog]
    page: PageInfo


class WebhookResponse(ApiModel):
    received: bool = True
    project_id: str | None = Field(default=None, alias="projectId")
    status: str | None = None


class UploadResponse(ApiModel):
    storage_path: str = Field(alias="storagePath")
    image_url: str | None = Field(default=None, alias="imageUrl")


# --- credits, packages and payments (API_CONTRACT.md Part II) ----------------


class ActiveDiscount(ApiModel):
    event_id: str = Field(alias="eventId")
    name: str
    discount_percent: int = Field(alias="discountPercent")
    ends_at: str = Field(alias="endsAt")


class CreditBalanceResponse(ApiModel):
    balance: int
    # The configured base price, before any event.
    generation_cost: int = Field(alias="generationCost")
    # What the next generation actually costs right now. This is the number the
    # Create screen shows: a user told "1" and charged "2" has been misled.
    effective_cost: int = Field(alias="effectiveCost")
    active_discount: ActiveDiscount | None = Field(default=None, alias="activeDiscount")
    lifetime_granted: int = Field(default=0, alias="lifetimeGranted")
    lifetime_spent: int = Field(default=0, alias="lifetimeSpent")


class CreditTransactionResponse(ApiModel):
    id: str
    delta: int
    balance_after: int = Field(alias="balanceAfter")
    reason: str
    ref_type: str | None = Field(default=None, alias="refType")
    ref_id: str | None = Field(default=None, alias="refId")
    note: str | None = None
    created_at: str = Field(alias="createdAt")


class CreditTransactionPage(ApiModel):
    items: list[CreditTransactionResponse]
    next_cursor: str | None = Field(default=None, alias="nextCursor")


class CreditPackageResponse(ApiModel):
    id: str
    name: str
    credits: int
    price_vnd: int = Field(alias="priceVnd")
    sort_order: int = Field(default=0, alias="sortOrder")


class CreditPackageList(ApiModel):
    items: list[CreditPackageResponse]


class PaymentCreate(ApiModel):
    # No default. `encodeDefaults = false` on the client drops any field still
    # equal to its default, so a defaulted package id would never be sent.
    package_id: str = Field(alias="packageId", min_length=1)


class PaymentResponse(ApiModel):
    id: str
    status: str
    package_id: str = Field(alias="packageId")
    amount_vnd: int = Field(alias="amountVnd")
    credits_granted: int = Field(alias="creditsGranted")
    balance: int
    # Always "simulated" today. Recorded rather than assumed, so the data says
    # what happened without anyone having to read ADR-010 first.
    method: str
    created_at: str = Field(alias="createdAt")
    completed_at: str | None = Field(default=None, alias="completedAt")


class LedgerDriftResponse(ApiModel):
    """Accounts whose cached balance disagrees with their ledger.

    `_refund_generation` deliberately swallows its own failures so a refund
    that fails cannot turn a failed generation into a 500. This is how that
    would otherwise-invisible failure becomes visible.
    """

    checked_at: str = Field(alias="checkedAt")
    drifted_user_ids: list[str] = Field(alias="driftedUserIds")
    healthy: bool
