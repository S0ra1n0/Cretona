from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.admin_service import AdminService
from app.auth import current_user_id, require_admin
from app.errors import AppError
from app.project_service import ProjectService
from app.prompt_service import PromptEnhancer
from app.schemas import (
    AdminAuditLogPage,
    AdminLogList,
    AdminUser,
    AdminUserPage,
    AdminUserUpdate,
    BackfillResponse,
    HealthResponse,
    MeResponse,
    MeUpdate,
    ProjectCancelResponse,
    ProjectCreate,
    ProjectPage,
    ProjectResponse,
    ProjectStatus,
    PromptEnhanceRequest,
    PromptEnhanceResponse,
    RoleName,
    StatsResponse,
    UploadResponse,
    UploadSignRequest,
    UploadSignResponse,
    WebhookResponse,
)
from app.storage import MAX_IMAGE_BYTES, StorageBackend, read_bounded, validate_upload_request
from app.users_service import UsersService

router = APIRouter()
UserId = Annotated[str, Depends(current_user_id)]
AdminId = Annotated[str, Depends(require_admin)]


def admin_service(request: Request) -> AdminService:
    return request.app.state.admin_service


def users_service(request: Request) -> UsersService:
    return request.app.state.users_service


def project_service(request: Request) -> ProjectService:
    return request.app.state.project_service


def prompt_enhancer(request: Request) -> PromptEnhancer:
    return request.app.state.prompt_enhancer


def media_storage(request: Request) -> StorageBackend:
    return request.app.state.storage


def request_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    return HealthResponse(version=request.app.state.settings_version)


@router.post("/prompts/enhance", response_model=PromptEnhanceResponse)
async def enhance_prompt(
    payload: PromptEnhanceRequest,
    _user_id: UserId,
    enhancer: Annotated[PromptEnhancer, Depends(prompt_enhancer)],
) -> PromptEnhanceResponse:
    return await enhancer.enhance(payload)


@router.get("/me", response_model=MeResponse)
def get_me(
    request: Request,
    user_id: UserId,
    service: Annotated[UsersService, Depends(users_service)],
) -> MeResponse:
    return service.get_me(user_id, request_base_url(request))


@router.patch("/me", response_model=MeResponse)
def update_me(
    payload: MeUpdate,
    request: Request,
    user_id: UserId,
    service: Annotated[UsersService, Depends(users_service)],
) -> MeResponse:
    # An omitted avatarPath must leave the existing picture alone, while an
    # explicit null clears it. Both arrive as None, so the caller's intent is
    # only recoverable from which fields were actually sent.
    return service.update_me(
        user_id,
        payload.username,
        avatar_path=payload.avatar_path,
        set_avatar="avatar_path" in payload.model_fields_set,
        base_url=request_base_url(request),
    )


@router.get("/admin/users", response_model=AdminUserPage)
def list_users(
    _admin_id: AdminId,
    service: Annotated[AdminService, Depends(admin_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: str | None = None,
    q: str | None = None,
    role: RoleName | None = None,
    is_disabled: Annotated[bool | None, Query(alias="isDisabled")] = None,
) -> AdminUserPage:
    return service.list_users(
        limit=limit,
        cursor=cursor,
        query=q,
        role=role,
        is_disabled=is_disabled,
    )


@router.patch("/admin/users/{user_id}", response_model=AdminUser)
def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    admin_id: AdminId,
    service: Annotated[AdminService, Depends(admin_service)],
) -> AdminUser:
    return service.update_user(admin_id, user_id, payload)


@router.get("/admin/stats", response_model=StatsResponse)
def admin_stats(
    _admin_id: AdminId,
    service: Annotated[AdminService, Depends(admin_service)],
    days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> StatsResponse:
    return service.stats(days)


@router.get("/admin/projects/{project_id}/logs", response_model=AdminLogList)
def admin_project_logs(
    project_id: str,
    _admin_id: AdminId,
    service: Annotated[AdminService, Depends(admin_service)],
) -> AdminLogList:
    items = service.get_generation_logs(project_id)
    return AdminLogList(items=items)


@router.get("/admin/audit-logs", response_model=AdminAuditLogPage)
def list_admin_audit_logs(
    _admin_id: AdminId,
    service: Annotated[AdminService, Depends(admin_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    action: str | None = None,
    actor_id: Annotated[str | None, Query(alias="actorId")] = None,
) -> AdminAuditLogPage:
    return service.list_audit_logs(
        limit=limit,
        cursor=cursor,
        action=action,
        actor_id=actor_id,
    )


@router.post("/admin/thumbnails/backfill", response_model=BackfillResponse)
def admin_backfill_thumbnails(
    request: Request,
    admin_id: AdminId,
    service: Annotated[AdminService, Depends(admin_service)],
    storage: Annotated[StorageBackend, Depends(media_storage)],
) -> BackfillResponse:
    thumbnails = request.app.state.project_service.thumbnails
    return service.backfill_thumbnails(storage, thumbnails, acting_admin_id=admin_id)


@router.post("/uploads/sign", response_model=UploadSignResponse)
def sign_upload(
    payload: UploadSignRequest,
    request: Request,
    user_id: UserId,
    storage: Annotated[StorageBackend, Depends(media_storage)],
) -> UploadSignResponse:
    """Hand the app a scoped, expiring URL to upload straight to storage.

    Image bytes never pass through this backend. The returned path embeds the
    caller's id, so the object is owned before it exists.
    """
    signed = storage.create_signed_upload(
        user_id,
        payload.content_type,
        payload.size_bytes,
        request_base_url(request),
    )
    return UploadSignResponse(
        uploadUrl=signed.upload_url,
        storagePath=signed.storage_path,
        token=signed.token,
        expiresAt=signed.expires_at,
    )


@router.post("/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_image(
    request: Request,
    user_id: UserId,
    storage: Annotated[StorageBackend, Depends(media_storage)],
    file: Annotated[UploadFile, File(...)],
) -> UploadResponse:
    """Direct multipart image upload endpoint."""
    # No default to a permitted type: an absent Content-Type must be rejected,
    # not silently treated as a JPEG.
    content_type = file.content_type or "application/octet-stream"
    # Type first, so an unsupported upload is refused before a byte is read.
    validate_upload_request(content_type, 0)
    data = await read_bounded(file, MAX_IMAGE_BYTES)
    storage_path = storage.store_image(user_id, content_type, data)
    image_url = storage.read_url(storage_path, request_base_url(request), video=False)
    return UploadResponse(storagePath=storage_path, imageUrl=image_url)


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    payload: ProjectCreate,
    request: Request,
    user_id: UserId,
    service: Annotated[ProjectService, Depends(project_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ProjectResponse:
    if idempotency_key:
        try:
            UUID(idempotency_key)
        except ValueError as exc:
            raise AppError(
                400,
                "VALIDATION_ERROR",
                "Idempotency-Key must be a UUID.",
                [{"field": "header.Idempotency-Key", "issue": "invalid_uuid"}],
            ) from exc
    return service.create(user_id, payload, idempotency_key, request_base_url(request))


@router.get("/projects", response_model=ProjectPage)
def list_projects(
    request: Request,
    user_id: UserId,
    service: Annotated[ProjectService, Depends(project_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: str | None = None,
    project_status: Annotated[ProjectStatus | None, Query(alias="status")] = None,
) -> ProjectPage:
    return service.list(
        user_id,
        limit=limit,
        status=project_status.value if project_status else None,
        cursor=cursor,
        base_url=request_base_url(request),
    )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    request: Request,
    user_id: UserId,
    service: Annotated[ProjectService, Depends(project_service)],
) -> ProjectResponse:
    return service.get(user_id, project_id, request_base_url(request))


@router.get("/projects/{project_id}/events")
async def stream_project_events(
    project_id: str,
    request: Request,
    user_id: UserId,
    service: Annotated[ProjectService, Depends(project_service)],
) -> StreamingResponse:
    import asyncio
    import json

    async def event_generator():
        base_url = request_base_url(request)
        for _ in range(60):
            try:
                proj = service.get(user_id, project_id, base_url)
                data = json.dumps(
                    {
                        "id": proj.id,
                        "status": str(proj.status),
                        "progressPercent": proj.progress_percent,
                        "stepMessage": proj.step_message,
                        "videoUrl": proj.video_url,
                        "thumbnailUrl": proj.thumbnail_url,
                        "errorMessage": proj.error_message,
                    }
                )
                yield f"event: project_update\ndata: {data}\n\n"
                if proj.status in (ProjectStatus.completed, ProjectStatus.failed):
                    break
                await asyncio.sleep(1.5)
            except Exception:
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    user_id: UserId,
    service: Annotated[ProjectService, Depends(project_service)],
) -> Response:
    service.delete(user_id, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project_id}/retry",
    response_model=ProjectResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_project(
    project_id: str,
    request: Request,
    user_id: UserId,
    service: Annotated[ProjectService, Depends(project_service)],
) -> ProjectResponse:
    return service.retry(user_id, project_id, request_base_url(request))


@router.post(
    "/projects/{project_id}/cancel",
    response_model=ProjectCancelResponse,
    status_code=status.HTTP_200_OK,
)
def cancel_project(
    project_id: str,
    user_id: UserId,
    service: Annotated[ProjectService, Depends(project_service)],
) -> ProjectCancelResponse:
    return service.cancel(user_id, project_id)


@router.post("/webhooks/{provider}", response_model=WebhookResponse)
async def handle_provider_webhook(
    provider: str,
    request: Request,
    service: Annotated[ProjectService, Depends(project_service)],
) -> WebhookResponse:
    body = await request.body()
    headers = dict(request.headers)
    return service.process_webhook(
        provider,
        headers,
        body,
        request_base_url(request),
    )
