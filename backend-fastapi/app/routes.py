from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from app.admin_service import AdminService
from app.auth import current_user_id, require_admin
from app.errors import AppError
from app.project_service import ProjectService
from app.prompt_service import PromptEnhancer
from app.schemas import (
    AdminUser,
    AdminUserPage,
    AdminUserUpdate,
    HealthResponse,
    ProjectCreate,
    ProjectPage,
    ProjectResponse,
    ProjectStatus,
    PromptEnhanceRequest,
    PromptEnhanceResponse,
    RoleName,
    StatsResponse,
    UploadSignRequest,
    UploadSignResponse,
)
from app.storage import StorageBackend

router = APIRouter()
UserId = Annotated[str, Depends(current_user_id)]
AdminId = Annotated[str, Depends(require_admin)]


def admin_service(request: Request) -> AdminService:
    return request.app.state.admin_service


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

