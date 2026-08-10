from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_payload(request: Request, error: AppError) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": {"code": error.code, "message": error.message},
        "requestId": getattr(request.state, "request_id", "unknown"),
    }
    if error.details:
        body["error"]["details"] = error.details
    return body


async def app_error_handler(request: Request, error: AppError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content=error_payload(request, error))


async def validation_error_handler(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    details = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        details.append({"field": location, "issue": str(item.get("type", "invalid"))})

    app_error = AppError(
        400,
        "VALIDATION_ERROR",
        "The request did not pass validation.",
        details,
    )
    return JSONResponse(status_code=400, content=error_payload(request, app_error))

