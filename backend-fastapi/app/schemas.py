from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ProjectStatus(StrEnum):
    pending = "pending"
    generating = "generating"
    completed = "completed"
    failed = "failed"


AspectRatio = Literal["16:9", "9:16", "1:1"]


class GenerationOptions(ApiModel):
    duration_seconds: Annotated[int, Field(alias="durationSeconds", ge=2, le=10)] = 5
    aspect_ratio: AspectRatio = Field(default="16:9", alias="aspectRatio")


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
