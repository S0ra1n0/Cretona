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


# Which inputs the server saw. Derived from the request rather than sent by
# the client, so the two can never disagree about what was asked for.
GenerationMode = Literal["text", "image", "text_image"]


class ProjectResponse(ApiModel):
    id: str
    title: str
    prompt: str | None
    mode: GenerationMode
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
    credits_granted: int = Field(default=0, alias="creditsGranted")
    credits_used: int = Field(default=0, alias="creditsUsed")
    # Simulated -- no real money moves (ADR-010). Labelled as such wherever it
    # is displayed, not only where it is defined.
    revenue_vnd: int = Field(default=0, alias="revenueVnd")


class DailyStat(ApiModel):
    date: str
    created: int
    completed: int
    failed: int
    # Signups. `created` counts projects, which is a different number.
    new_users: int = Field(default=0, alias="newUsers")
    credits_granted: int = Field(default=0, alias="creditsGranted")
    credits_used: int = Field(default=0, alias="creditsUsed")
    revenue_vnd: int = Field(default=0, alias="revenueVnd")


class EventStat(ApiModel):
    event_id: str = Field(alias="eventId")
    code: str
    name: str
    claims: int
    credits_granted: int = Field(alias="creditsGranted")
    remaining_slots: int | None = Field(default=None, alias="remainingSlots")


class StatsResponse(ApiModel):
    totals: StatsTotals
    projects_by_status: dict[str, int] = Field(alias="projectsByStatus")
    projects_by_provider: dict[str, int] = Field(alias="projectsByProvider")
    failure_rate: float = Field(alias="failureRate")
    daily: list[DailyStat]
    events: list[EventStat] = Field(default_factory=list)


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


class EventResponse(ApiModel):
    id: str
    code: str
    name: str
    description: str | None = None
    kind: str
    bonus_credits: int | None = Field(default=None, alias="bonusCredits")
    discount_percent: int | None = Field(default=None, alias="discountPercent")
    recurrence: str
    is_active_now: bool = Field(alias="isActiveNow")
    active_until: str | None = Field(default=None, alias="activeUntil")
    next_active_at: str | None = Field(default=None, alias="nextActiveAt")
    # The one flag the app's button binds to. Computed server-side so the rule
    # that gives credits away lives in exactly one place.
    claimable: bool
    claimed_this_period: bool = Field(alias="claimedThisPeriod")
    remaining_slots: int | None = Field(default=None, alias="remainingSlots")


class EventPage(ApiModel):
    items: list[EventResponse]
    next_cursor: str | None = Field(default=None, alias="nextCursor")


class EventClaimResponse(ApiModel):
    credits_granted: int = Field(alias="creditsGranted")
    balance: int
    transaction_id: str = Field(alias="transactionId")


# --- admin: credits, packages, events (API_CONTRACT.md Part II §9) -----------


class AdminCreditAdjust(ApiModel):
    # No default: `encodeDefaults = false` on the client would drop a defaulted
    # field, and a dropped delta is an adjustment of nothing.
    delta: int
    note: str | None = None


class AdminCreditAdjustResponse(ApiModel):
    user_id: str = Field(alias="userId")
    delta: int
    balance: int
    transaction_id: str = Field(alias="transactionId")


class AdminSettingsResponse(ApiModel):
    generation_cost_credits: int = Field(alias="generationCostCredits")


class AdminSettingsUpdate(ApiModel):
    generation_cost_credits: Annotated[
        int, Field(alias="generationCostCredits", ge=1, le=1000)
    ]


class AdminPackageCreate(ApiModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    credits: Annotated[int, Field(gt=0, le=100000)]
    price_vnd: Annotated[int, Field(alias="priceVnd", ge=0)]
    sort_order: int = Field(default=0, alias="sortOrder")


class AdminPackageUpdate(ApiModel):
    name: str | None = None
    credits: Annotated[int | None, Field(gt=0, le=100000)] = None
    price_vnd: Annotated[int | None, Field(alias="priceVnd", ge=0)] = None
    sort_order: int | None = Field(default=None, alias="sortOrder")
    is_active: bool | None = Field(default=None, alias="isActive")


class AdminPackage(ApiModel):
    id: str
    name: str
    credits: int
    price_vnd: int = Field(alias="priceVnd")
    sort_order: int = Field(alias="sortOrder")
    is_active: bool = Field(alias="isActive")


class AdminPackageList(ApiModel):
    items: list[AdminPackage]


class AdminEventCreate(ApiModel):
    code: Annotated[str, Field(min_length=1, max_length=40)]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: str | None = None
    kind: Literal["grant", "discount"]
    bonus_credits: Annotated[int | None, Field(alias="bonusCredits", gt=0)] = None
    discount_percent: Annotated[
        int | None, Field(alias="discountPercent", ge=1, le=100)
    ] = None
    recurrence: Literal["once", "daily", "weekly"] = "once"
    # 'sat,sun'. Free text rather than an enum list because the database stores
    # it as one string and the service parses it in one place.
    active_days: str | None = Field(default=None, alias="activeDays")
    # Minutes from local midnight: 1200 is 20:00 Vietnam time.
    active_from_minute: Annotated[
        int | None, Field(alias="activeFromMinute", ge=0, le=1440)
    ] = None
    active_to_minute: Annotated[
        int | None, Field(alias="activeToMinute", ge=0, le=1440)
    ] = None
    starts_at: str = Field(alias="startsAt")
    ends_at: str = Field(alias="endsAt")
    max_claims: Annotated[int | None, Field(alias="maxClaims", gt=0)] = None
    auto_grant: bool = Field(default=False, alias="autoGrant")


class AdminEventUpdate(ApiModel):
    name: str | None = None
    description: str | None = None
    bonus_credits: Annotated[int | None, Field(alias="bonusCredits", gt=0)] = None
    discount_percent: Annotated[
        int | None, Field(alias="discountPercent", ge=1, le=100)
    ] = None
    active_days: str | None = Field(default=None, alias="activeDays")
    active_from_minute: Annotated[
        int | None, Field(alias="activeFromMinute", ge=0, le=1440)
    ] = None
    active_to_minute: Annotated[
        int | None, Field(alias="activeToMinute", ge=0, le=1440)
    ] = None
    starts_at: str | None = Field(default=None, alias="startsAt")
    ends_at: str | None = Field(default=None, alias="endsAt")
    max_claims: Annotated[int | None, Field(alias="maxClaims", gt=0)] = None
    is_active: bool | None = Field(default=None, alias="isActive")


class AdminEvent(ApiModel):
    id: str
    code: str
    name: str
    description: str | None = None
    kind: str
    bonus_credits: int | None = Field(default=None, alias="bonusCredits")
    discount_percent: int | None = Field(default=None, alias="discountPercent")
    recurrence: str
    active_days: str | None = Field(default=None, alias="activeDays")
    active_from_minute: int | None = Field(default=None, alias="activeFromMinute")
    active_to_minute: int | None = Field(default=None, alias="activeToMinute")
    starts_at: str = Field(alias="startsAt")
    ends_at: str = Field(alias="endsAt")
    max_claims: int | None = Field(default=None, alias="maxClaims")
    auto_grant: bool = Field(alias="autoGrant")
    is_active: bool = Field(alias="isActive")


class AdminEventList(ApiModel):
    items: list[AdminEvent]


class AdminEventClaim(ApiModel):
    id: str
    user_id: str = Field(alias="userId")
    period_key: str = Field(alias="periodKey")
    credits_granted: int = Field(alias="creditsGranted")
    created_at: str = Field(alias="createdAt")


class AdminEventClaimList(ApiModel):
    items: list[AdminEventClaim]
    total: int


class AdminPayment(ApiModel):
    id: str
    user_id: str = Field(alias="userId")
    package_id: str = Field(alias="packageId")
    amount_vnd: int = Field(alias="amountVnd")
    credits_granted: int = Field(alias="creditsGranted")
    method: str
    status: str
    created_at: str = Field(alias="createdAt")
    completed_at: str | None = Field(default=None, alias="completedAt")


class AdminPaymentPage(ApiModel):
    items: list[AdminPayment]
    next_cursor: str | None = Field(default=None, alias="nextCursor")


class AdminCreditTransaction(ApiModel):
    id: str
    user_id: str = Field(alias="userId")
    delta: int
    balance_after: int = Field(alias="balanceAfter")
    reason: str
    ref_type: str | None = Field(default=None, alias="refType")
    ref_id: str | None = Field(default=None, alias="refId")
    note: str | None = None
    created_at: str = Field(alias="createdAt")


class AdminCreditTransactionPage(ApiModel):
    items: list[AdminCreditTransaction]
    next_cursor: str | None = Field(default=None, alias="nextCursor")
