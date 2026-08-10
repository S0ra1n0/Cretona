from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.database import Database
from app.errors import AppError, app_error_handler, error_payload, validation_error_handler
from app.project_service import ProjectService
from app.prompt_service import PromptEnhancer
from app.providers import FakeVideoProvider, ProviderRegistry
from app.routes import router

APP_VERSION = "0.1.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    database = Database(active_settings.resolved_database_path())
    provider = FakeVideoProvider(
        polls_before_complete=active_settings.fake_polls_before_complete,
        video_filename=active_settings.fake_video_filename,
    )
    providers = ProviderRegistry([provider], active_settings.default_video_provider)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        active_settings.resolved_media_dir().mkdir(parents=True, exist_ok=True)
        database.initialize()
        yield

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
    api.state.project_service = ProjectService(database, providers)
    api.state.prompt_enhancer = PromptEnhancer(active_settings)

    @api.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
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
    async def internal_error_handler(request: Request, _error: Exception) -> JSONResponse:
        error = AppError(500, "INTERNAL_ERROR", "An unexpected server error occurred.")
        return JSONResponse(status_code=500, content=error_payload(request, error))

    api.include_router(router, prefix="/api/v1")
    api.mount(
        "/media",
        StaticFiles(directory=active_settings.resolved_media_dir(), check_dir=False),
        name="media",
    )
    return api


app = create_app()
