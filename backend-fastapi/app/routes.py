from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from app.auth import current_user_id
from app.errors import AppError
from app.project_service import ProjectService
from app.prompt_service import PromptEnhancer
from app.schemas import (
    HealthResponse,
    ProjectCreate,
    ProjectPage,
    ProjectResponse,
    ProjectStatus,
    PromptEnhanceRequest,
    PromptEnhanceResponse,
)

router = APIRouter()
UserId = Annotated[str, Depends(current_user_id)]


def project_service(request: Request) -> ProjectService:
    return request.app.state.project_service


def prompt_enhancer(request: Request) -> PromptEnhancer:
    return request.app.state.prompt_enhancer


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

