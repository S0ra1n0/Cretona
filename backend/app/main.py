from __future__ import annotations

import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.admin_service import AdminService
from app.config import Settings, get_settings
from app.database import Database
from app.errors import AppError, app_error_handler, error_payload, validation_error_handler
from app.generation_log_retention import GenerationLogRetentionWorker
from app.generation_log_service import GenerationLogService
from app.jwks import JwksCache
from app.logging_setup import configure_logging
from app.poller import JobPoller
from app.postgres import PostgresDatabase
from app.project_service import ProjectService
from app.prompt_service import PromptEnhancer
from app.providers import (
    CloudAiVideoProvider,
    LocalModelVideoProvider,
    MockVideoProvider,
    ProviderRegistry,
)
from app.quota_service import QuotaService
from app.rate_limit import WINDOW_SECONDS, RateLimiter, bucket_for, caller_key
from app.routes import router
from app.storage import LocalStorage, SupabaseStorage
from app.thumbnails import ThumbnailGenerator
from app.users_service import UsersService

APP_VERSION = "0.1.0"


def build_database(settings: Settings) -> Database | PostgresDatabase:
    """Select the persistence adapter from the config profile (ADR-008).

    Both satisfy the same repository contract, so nothing downstream branches
    on which one is active.
    """
    if settings.database_backend == "postgres":
        return PostgresDatabase(settings.database_url.get_secret_value())
    return Database(settings.resolved_database_path())


def build_storage(settings: Settings) -> LocalStorage | SupabaseStorage:
    """Select the media backend from the config profile.

    Android is unaffected either way: it consumes whatever URL the response
    carries and never learns where the bytes live.
    """
    if settings.storage_backend == "supabase":
        return SupabaseStorage(
            base_url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key.get_secret_value(),
            uploads_bucket=settings.supabase_uploads_bucket,
            videos_bucket=settings.supabase_videos_bucket,
            signed_url_ttl_seconds=settings.signed_url_ttl_seconds,
            media_dir=settings.resolved_media_dir(),
        )
    return LocalStorage(settings.resolved_media_dir())


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    logger = configure_logging(active_settings.log_level)
    database = build_database(active_settings)
    storage = build_storage(active_settings)
    mock_provider = MockVideoProvider(
        polls_before_complete=active_settings.fake_polls_before_complete,
        video_filename=active_settings.fake_video_filename,
    )
    cloud_provider = CloudAiVideoProvider(
        api_key=active_settings.cloud_ai_api_key.get_secret_value()
        or active_settings.real_ai_api_key.get_secret_value(),
        endpoint=active_settings.cloud_ai_endpoint or active_settings.real_ai_endpoint,
        video_filename=active_settings.fake_video_filename,
    )
    local_provider = LocalModelVideoProvider(
        endpoint=active_settings.local_model_endpoint,
        video_filename=active_settings.fake_video_filename,
    )
    providers = ProviderRegistry(
        [mock_provider, cloud_provider, local_provider],
        active_settings.default_video_provider,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        active_settings.resolved_media_dir().mkdir(parents=True, exist_ok=True)
        database.initialize()
        api.state.generation_log_retention.start()
        api.state.poller.start()
        try:
            yield
        finally:
            await api.state.generation_log_retention.stop()
            await api.state.poller.stop()
            close = getattr(database, "close", None)
            if close is not None:
                close()

    api = FastAPI(
        title="Cretona API",
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if active_settings.environment != "production" else None,
        redoc_url=None,
    )
    api.state.settings = active_settings
    api.state.settings_version = APP_VERSION
    api.state.database = database
    api.state.storage = storage
    api.state.jwks = (
        JwksCache(active_settings.resolved_jwks_url())
        if active_settings.supabase_jwt_algorithm == "ES256"
        else None
    )
    api.state.admin_service = AdminService(database)
    api.state.quota_service = QuotaService(database, active_settings)
    api.state.users_service = UsersService(database, api.state.quota_service)
    api.state.generation_log = GenerationLogService(database)
    api.state.generation_log_retention = GenerationLogRetentionWorker(
        api.state.generation_log, active_settings
    )
    limiter = RateLimiter(
        default_per_minute=active_settings.rate_limit_default_per_min,
        generation_per_minute=active_settings.rate_limit_generation_per_min,
        shared_store=database if database.backend == "postgres" else None,
    )
    api.state.rate_limiter = limiter
    api.state.project_service = ProjectService(
        database,
        providers,
        active_settings,
        storage,
        api.state.quota_service,
        api.state.generation_log,
        ThumbnailGenerator(
            ffmpeg_path=active_settings.ffmpeg_path,
            enabled=active_settings.thumbnails_enabled,
            seek_seconds=active_settings.thumbnail_seek_seconds,
        ),
    )
    api.state.prompt_enhancer = PromptEnhancer(active_settings)
    api.state.poller = JobPoller(database, api.state.project_service, active_settings)

    @api.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
        started = perf_counter()

        limit_headers: dict[str, str] = {}
        if active_settings.rate_limit_enabled and request.url.path != "/api/v1/health":
            key = caller_key(
                request.headers.get("Authorization"),
                request.headers.get("X-Debug-User-Id"),
                request.client.host if request.client else "unknown",
            )
            bucket = bucket_for(request.method, request.url.path)
            allowed, limit, remaining = limiter.check(key, bucket)
            limit_headers = {
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(WINDOW_SECONDS),
            }
            if not allowed:
                error = AppError(429, "RATE_LIMITED", "Too many requests. Please slow down.")
                refused = JSONResponse(
                    status_code=429,
                    content=error_payload(request, error),
                    headers={**limit_headers, "Retry-After": str(int(WINDOW_SECONDS))},
                )
                refused.headers["X-Request-ID"] = request.state.request_id
                return refused

        response = await call_next(request)
        for header, value in limit_headers.items():
            response.headers[header] = value
        response.headers["X-Request-ID"] = request.state.request_id

        # Deliberately field-by-field. Logging the request object wholesale is
        # how an Authorization header ends up in a log aggregator.
        should_log = (
            response.status_code >= 400
            or active_settings.request_log_sample_rate >= 1.0
            or random.random() < active_settings.request_log_sample_rate
        )
        if should_log:
            logger.info(
                "request",
                extra={
                    "requestId": request.state.request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "durationMs": round((perf_counter() - started) * 1000, 2),
                },
            )
        return response

    if active_settings.environment != "production":
        api.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    api.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    api.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]

    @api.exception_handler(Exception)
    async def internal_error_handler(request: Request, error: Exception) -> JSONResponse:
        # The caller gets a generic message; the stack trace stays server-side.
        logger.error(
            "unhandled_error",
            exc_info=error,
            extra={
                "requestId": getattr(request.state, "request_id", "unknown"),
                "path": request.url.path,
            },
        )
        safe = AppError(500, "INTERNAL_ERROR", "An unexpected server error occurred.")
        return JSONResponse(status_code=500, content=error_payload(request, safe))

    api.include_router(router, prefix="/api/v1")
    api.mount(
        "/media",
        StaticFiles(directory=active_settings.resolved_media_dir(), check_dir=False),
        name="media",
    )
    return api


app = create_app()
