from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

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
    duration_seconds: int | None = Field(alias="durationSeconds")
    aspect_ratio: AspectRatio = Field(alias="aspectRatio")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    completed_at: datetime | None = Field(alias="completedAt")


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

