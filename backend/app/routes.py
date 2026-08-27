from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.admin_credit_service import AdminCreditService
from app.admin_service import AdminService
from app.auth import current_user_id, require_admin
from app.credit_service import CreditService
from app.errors import AppError
from app.event_service import EventService
from app.health import require_database_connection
from app.metrics import format_prometheus_metrics
from app.payment_service import PaymentService
from app.project_service import ProjectService
from app.prompt_service import PromptEnhancer
from app.schemas import (
    ActiveDiscount,
    AdminAuditLogPage,
    AdminCreditAdjust,
    AdminCreditAdjustResponse,
    AdminCreditTransaction,
    AdminCreditTransactionPage,
    AdminEvent,
    AdminEventClaim,
    AdminEventClaimList,
    AdminEventCreate,
    AdminEventList,
    AdminEventUpdate,
    AdminLogList,
    AdminMetricsResponse,
    AdminPackage,
    AdminPackageCreate,
    AdminPackageList,
    AdminPackageUpdate,
    AdminPayment,
    AdminPaymentPage,
    AdminSettingsResponse,
    AdminSettingsUpdate,
    AdminUser,
    AdminUserPage,
    AdminUserUpdate,
    BackfillResponse,
    CreditBalanceResponse,
    CreditPackageList,
    CreditPackageResponse,
    CreditTransactionPage,
    CreditTransactionResponse,
    EventClaimResponse,
    EventPage,
    EventResponse,
    HealthResponse,
    LedgerDriftResponse,
    MeResponse,
    MeUpdate,
    PageInfo,
    PaymentCreate,
    PaymentResponse,
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
    require_database_connection(request.app.state.database)
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
    # An omitted field must leave the existing value alone, while a sent one
    # clears or replaces it. Both arrive as None, so the caller's intent is
    # only recoverable from which fields were actually sent.
    sent = payload.model_fields_set
    return service.update_me(
        user_id,
        payload.username,
        avatar_path=payload.avatar_path,
        set_avatar="avatar_path" in sent,
        gender=payload.gender,
        set_gender="gender" in sent,
        birthday=payload.birthday,
        set_birthday="birthday" in sent,
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


@router.get("/admin/metrics", response_model=AdminMetricsResponse)
def admin_system_metrics(
    request: Request,
    _admin_id: AdminId,
    service: Annotated[AdminService, Depends(admin_service)],
    storage: Annotated[StorageBackend, Depends(media_storage)],
) -> AdminMetricsResponse:
    start_time = getattr(request.app.state, "start_time", 0.0)
    return service.get_system_metrics(storage, start_time)


@router.get("/metrics", response_class=Response)
def prometheus_metrics(
    request: Request,
    _admin_id: AdminId,
    service: Annotated[AdminService, Depends(admin_service)],
    storage: Annotated[StorageBackend, Depends(media_storage)],
) -> Response:
    start_time = getattr(request.app.state, "start_time", 0.0)
    sys_metrics = service.get_system_metrics(storage, start_time)
    body = format_prometheus_metrics(
        uptime_seconds=sys_metrics.uptime_seconds,
        active_jobs=sys_metrics.active_jobs,
        completed_jobs=sys_metrics.completed_jobs,
        failed_jobs=sys_metrics.failed_jobs,
        memory_rss_mb=sys_metrics.memory_rss_mb,
        database_backend=sys_metrics.database_backend,
        database_status=sys_metrics.database_status,
        storage_backend=sys_metrics.storage_backend,
    )
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


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
    storage_path = await asyncio.to_thread(storage.store_image, user_id, content_type, data)
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


# --- credits, packages and payments (API_CONTRACT.md Part II) ----------------


def credit_service(request: Request) -> CreditService:
    return request.app.state.credit_service


def payment_service(request: Request) -> PaymentService:
    return request.app.state.payment_service


@router.get("/me/credits", response_model=CreditBalanceResponse)
def get_credit_balance(
    user_id: UserId,
    credits: Annotated[CreditService, Depends(credit_service)],
    events: Annotated[EventService, Depends(event_service)],
) -> CreditBalanceResponse:
    granted, spent = credits.totals(user_id)
    base = credits.generation_cost()
    discount = events.active_discount()

    return CreditBalanceResponse(
        balance=credits.balance(user_id),
        generationCost=base,
        # What the next generation costs right now. The Create screen shows
        # this, never `generationCost`: a user quoted 1 and charged 2 has been
        # misled, and during Hot Hours those are different numbers.
        effectiveCost=CreditService.effective_cost(
            base, discount["discount_percent"] if discount else None
        ),
        activeDiscount=(
            ActiveDiscount(
                eventId=str(discount["id"]),
                name=discount["name"],
                discountPercent=int(discount["discount_percent"]),
                endsAt=events.active_until(discount, datetime.now(UTC)) or "",
            )
            if discount
            else None
        ),
        lifetimeGranted=granted,
        lifetimeSpent=spent,
    )


@router.get("/me/credits/transactions", response_model=CreditTransactionPage)
def list_credit_transactions(
    user_id: UserId,
    credits: Annotated[CreditService, Depends(credit_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> CreditTransactionPage:
    rows, next_cursor = credits.history(user_id, limit=limit, cursor=cursor)
    return CreditTransactionPage(
        items=[
            CreditTransactionResponse(
                id=str(row["id"]),
                delta=row["delta"],
                balanceAfter=row["balance_after"],
                reason=row["reason"],
                refType=row.get("ref_type"),
                refId=row.get("ref_id"),
                note=row.get("note"),
                createdAt=row["created_at"],
            )
            for row in rows
        ],
        nextCursor=next_cursor,
    )


@router.get("/credit-packages", response_model=CreditPackageList)
def list_credit_packages(
    _user_id: UserId,
    payments: Annotated[PaymentService, Depends(payment_service)],
) -> CreditPackageList:
    return CreditPackageList(
        items=[
            CreditPackageResponse(
                id=str(row["id"]),
                name=row["name"],
                credits=row["credits"],
                priceVnd=row["price_vnd"],
                sortOrder=row.get("sort_order", 0),
            )
            for row in payments.list_packages()
        ]
    )


@router.post(
    "/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_payment(
    payload: PaymentCreate,
    user_id: UserId,
    payments: Annotated[PaymentService, Depends(payment_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> PaymentResponse:
    """Buy a credit package. No real money moves -- see ADR-010.

    The key is required, not optional as it is on project creation: a replayed
    generation wastes a slot, a replayed purchase grants credits twice.
    """
    if not idempotency_key:
        raise AppError(
            400,
            "VALIDATION_ERROR",
            "Idempotency-Key is required so a retried purchase cannot grant twice.",
            [{"field": "header.Idempotency-Key", "issue": "required"}],
        )
    try:
        UUID(idempotency_key)
    except ValueError as exc:
        raise AppError(
            400,
            "VALIDATION_ERROR",
            "Idempotency-Key must be a UUID.",
            [{"field": "header.Idempotency-Key", "issue": "invalid_uuid"}],
        ) from exc

    payment = payments.purchase(user_id, payload.package_id, idempotency_key)
    return PaymentResponse(
        id=str(payment["id"]),
        status=payment["status"],
        packageId=str(payment["package_id"]),
        amountVnd=payment["amount_vnd"],
        creditsGranted=payment["credits_granted"],
        balance=payment["balance"],
        method=payment["method"],
        createdAt=payment["created_at"],
        completedAt=payment.get("completed_at"),
    )


@router.get("/admin/credits/drift", response_model=LedgerDriftResponse)
def get_ledger_drift(
    request: Request,
    _admin_id: Annotated[str, Depends(require_admin)],
) -> LedgerDriftResponse:
    """Accounts whose cached balance no longer matches their ledger.

    The ledger is the truth and `users.credit_balance` is a cache kept in the
    same transaction, so this should always be empty. It exists because
    `_refund_generation` swallows its own errors on purpose -- a refund that
    raised would turn a failed generation into a 500 and strand the project --
    which means a failed refund is otherwise silent. This is the only thing
    that would surface one.
    """
    drifted = request.app.state.database.ledger_drift()
    return LedgerDriftResponse(
        checkedAt=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        driftedUserIds=[str(user_id) for user_id in drifted],
        healthy=not drifted,
    )


def event_service(request: Request) -> EventService:
    return request.app.state.event_service


def _event_response(row: dict) -> EventResponse:
    return EventResponse(
        id=str(row["id"]),
        code=row["code"],
        name=row["name"],
        description=row.get("description"),
        kind=row["kind"],
        bonusCredits=row.get("bonus_credits"),
        discountPercent=row.get("discount_percent"),
        recurrence=row["recurrence"],
        isActiveNow=row["is_active_now"],
        activeUntil=row.get("active_until"),
        nextActiveAt=row.get("next_active_at"),
        claimable=row["claimable"],
        claimedThisPeriod=row["claimed_this_period"],
        remainingSlots=row.get("remaining_slots"),
    )


@router.get("/events", response_model=EventPage)
def list_events(
    user_id: UserId,
    events: Annotated[EventService, Depends(event_service)],
) -> EventPage:
    return EventPage(
        items=[_event_response(row) for row in events.list_for(user_id)],
        nextCursor=None,
    )


@router.post("/events/{event_id}/claim", response_model=EventClaimResponse)
def claim_event(
    event_id: str,
    user_id: UserId,
    events: Annotated[EventService, Depends(event_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> EventClaimResponse:
    """Claim a grant event.

    No idempotency key is needed to be safe: the unique index on
    (event, user, period) already makes a second attempt a refusal rather than
    a second grant. The header is accepted so the app can send one uniformly.
    """
    result = events.claim(user_id, event_id)
    return EventClaimResponse(
        creditsGranted=result["credits_granted"],
        balance=result["balance"],
        transactionId=result["transaction_id"],
    )


# --- admin: credits, packages, events, payments (S-16) -----------------------


def admin_credits(request: Request) -> AdminCreditService:
    return request.app.state.admin_credit_service


AdminId = Annotated[str, Depends(require_admin)]


def _admin_tx(row: dict) -> AdminCreditTransaction:
    return AdminCreditTransaction(
        id=str(row["id"]),
        userId=str(row["user_id"]),
        delta=row["delta"],
        balanceAfter=row["balance_after"],
        reason=row["reason"],
        refType=row.get("ref_type"),
        refId=row.get("ref_id"),
        note=row.get("note"),
        createdAt=row["created_at"],
    )


def _admin_event(row: dict) -> AdminEvent:
    return AdminEvent(
        id=str(row["id"]),
        code=row["code"],
        name=row["name"],
        description=row.get("description"),
        kind=row["kind"],
        bonusCredits=row.get("bonus_credits"),
        discountPercent=row.get("discount_percent"),
        recurrence=row["recurrence"],
        activeDays=row.get("active_days"),
        activeFromMinute=row.get("active_from_minute"),
        activeToMinute=row.get("active_to_minute"),
        startsAt=row["starts_at"],
        endsAt=row["ends_at"],
        maxClaims=row.get("max_claims"),
        autoGrant=bool(row.get("auto_grant")),
        isActive=bool(row.get("is_active")),
    )


def _admin_package(row: dict) -> AdminPackage:
    return AdminPackage(
        id=str(row["id"]),
        name=row["name"],
        credits=row["credits"],
        priceVnd=row["price_vnd"],
        sortOrder=row.get("sort_order", 0),
        isActive=bool(row.get("is_active", True)),
    )


@router.post(
    "/admin/users/{user_id}/credits",
    response_model=AdminCreditAdjustResponse,
)
def adjust_user_credits(
    user_id: str,
    payload: AdminCreditAdjust,
    admin_id: AdminId,
    service: Annotated[AdminCreditService, Depends(admin_credits)],
) -> AdminCreditAdjustResponse:
    """Add or remove credits from an account (brief §3).

    The adjustment and its audit row are written in one transaction, so an
    admin cannot change a balance without leaving a record of having done it.
    """
    result = service.adjust(admin_id, user_id, payload.delta, payload.note)
    return AdminCreditAdjustResponse(
        userId=result["userId"],
        delta=result["delta"],
        balance=result["balance"],
        transactionId=result["transactionId"],
    )


@router.get("/admin/credit-transactions", response_model=AdminCreditTransactionPage)
def admin_list_credit_transactions(
    _admin_id: AdminId,
    service: Annotated[AdminCreditService, Depends(admin_credits)],
    userId: str | None = None,
    reason: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> AdminCreditTransactionPage:
    rows, next_cursor = service.transactions(
        user_id=userId, reason=reason, limit=limit, cursor=cursor
    )
    return AdminCreditTransactionPage(
        items=[_admin_tx(row) for row in rows], nextCursor=next_cursor
    )


@router.get("/admin/settings", response_model=AdminSettingsResponse)
def admin_get_settings(
    _admin_id: AdminId,
    service: Annotated[AdminCreditService, Depends(admin_credits)],
) -> AdminSettingsResponse:
    values = service.settings()
    return AdminSettingsResponse(
        generationCostCredits=int(values.get("generation_cost_credits") or 1)
    )


@router.patch("/admin/settings", response_model=AdminSettingsResponse)
def admin_update_settings(
    payload: AdminSettingsUpdate,
    admin_id: AdminId,
    service: Annotated[AdminCreditService, Depends(admin_credits)],
) -> AdminSettingsResponse:
    """Set what a generation costs -- the brief's "cấu hình chi phí tạo video".

    Takes effect on the next charge, because the cost is read at charge time
    rather than cached anywhere.
    """
    values = service.update_setting(
        admin_id, "generation_cost_credits", str(payload.generation_cost_credits)
    )
    return AdminSettingsResponse(
        generationCostCredits=int(values.get("generation_cost_credits") or 1)
    )


@router.get("/admin/credit-packages", response_model=AdminPackageList)
def admin_list_packages(
    _admin_id: AdminId,
    service: Annotated[AdminCreditService, Depends(admin_credits)],
) -> AdminPackageList:
    # Inactive ones included: the admin screen manages them, and a package you
    # cannot see is a package you cannot re-enable.
    return AdminPackageList(items=[_admin_package(row) for row in service.packages()])


@router.post(
    "/admin/credit-packages",
    response_model=AdminPackage,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_package(
    payload: AdminPackageCreate,
    admin_id: AdminId,
    service: Annotated[AdminCreditService, Depends(admin_credits)],
) -> AdminPackage:
    return _admin_package(
        service.create_package(admin_id, payload.model_dump(exclude_none=True))
    )


@router.patch("/admin/credit-packages/{package_id}", response_model=AdminPackage)
def admin_update_package(
    package_id: str,
    payload: AdminPackageUpdate,
    admin_id: AdminId,
    service: Annotated[AdminCreditService, Depends(admin_credits)],
) -> AdminPackage:
    """Change a package, or take it off sale with `isActive: false`.

    There is no delete: `payments` reference packages, and a purchase history
    that loses the thing purchased is not a history.
    """
    return _admin_package(
        service.update_package(
            admin_id, package_id, payload.model_dump(exclude_unset=True)
        )
    )


@router.get("/admin/events", response_model=AdminEventList)
def admin_list_events(
    _admin_id: AdminId,
    service: Annotated[AdminCreditService, Depends(admin_credits)],
) -> AdminEventList:
    return AdminEventList(items=[_admin_event(row) for row in service.events()])


@router.post(
    "/admin/events", response_model=AdminEvent, status_code=status.HTTP_201_CREATED
)
def admin_create_event(
    payload: AdminEventCreate,
    admin_id: AdminId,
    service: Annotated[AdminCreditService, Depends(admin_credits)],
) -> AdminEvent:
    """Create a promotion (brief §3: window, conditions, grant, cap, status)."""
    return _admin_event(service.create_event(admin_id, payload.model_dump()))


@router.patch("/admin/events/{event_id}", response_model=AdminEvent)
def admin_update_event(
    event_id: str,
    payload: AdminEventUpdate,
    admin_id: AdminId,
    service: Annotated[AdminCreditService, Depends(admin_credits)],
) -> AdminEvent:
    return _admin_event(
        service.update_event(admin_id, event_id, payload.model_dump(exclude_unset=True))
    )


@router.get("/admin/events/{event_id}/claims", response_model=AdminEventClaimList)
def admin_list_event_claims(
    event_id: str,
    _admin_id: AdminId,
    service: Annotated[AdminCreditService, Depends(admin_credits)],
) -> AdminEventClaimList:
    """Who took a campaign up -- the brief's "hiệu quả các đợt khuyến mãi"."""
    claims = service.claims(event_id)
    return AdminEventClaimList(
        items=[
            AdminEventClaim(
                id=str(row["id"]),
                userId=str(row["user_id"]),
                periodKey=row["period_key"],
                creditsGranted=row["credits_granted"],
                createdAt=row["created_at"],
            )
            for row in claims
        ],
        total=len(claims),
    )


@router.get("/admin/payments", response_model=AdminPaymentPage)
def admin_list_payments(
    _admin_id: AdminId,
    service: Annotated[AdminCreditService, Depends(admin_credits)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> AdminPaymentPage:
    """Where the revenue figure comes from. No real money moves -- ADR-010."""
    rows, next_cursor = service.payments(
        status=status_filter, limit=limit, cursor=cursor
    )
    return AdminPaymentPage(
        items=[
            AdminPayment(
                id=str(row["id"]),
                userId=str(row["user_id"]),
                packageId=str(row["package_id"]),
                amountVnd=row["amount_vnd"],
                creditsGranted=row["credits_granted"],
                method=row["method"],
                status=row["status"],
                createdAt=row["created_at"],
                completedAt=row.get("completed_at"),
            )
            for row in rows
        ],
        nextCursor=next_cursor,
    )


@router.get("/admin/projects", response_model=ProjectPage)
def admin_list_projects(
    request: Request,
    _admin_id: AdminId,
    service: Annotated[ProjectService, Depends(project_service)],
    status_filter: Annotated[ProjectStatus | None, Query(alias="status")] = None,
    userId: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> ProjectPage:
    """Every user's videos, for moderation (brief §3: "quản lý ... video")."""
    rows, next_cursor = request.app.state.database.list_all_projects(
        status=status_filter.value if status_filter else None,
        owner_id=userId,
        limit=limit,
        cursor=cursor,
    )
    base_url = request_base_url(request)
    return ProjectPage(
        items=[service.to_response(row, base_url) for row in rows],
        page=PageInfo(nextCursor=next_cursor, hasMore=next_cursor is not None),
    )
