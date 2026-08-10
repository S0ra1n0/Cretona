from __future__ import annotations

from uuid import UUID

from fastapi import Header, Request

from app.config import Settings
from app.errors import AppError


def current_user_id(
    request: Request,
    x_debug_user_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> str:
    settings: Settings = request.app.state.settings

    if settings.auth_mode == "dev":
        candidate = x_debug_user_id or settings.dev_user_id
        try:
            return str(UUID(candidate))
        except ValueError as exc:
            raise AppError(
                400,
                "VALIDATION_ERROR",
                "X-Debug-User-Id must be a UUID in development mode.",
                [{"field": "header.X-Debug-User-Id", "issue": "invalid_uuid"}],
            ) from exc

    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(401, "UNAUTHENTICATED", "A bearer token is required.")

    # Deliberately fail closed until the Supabase JWT verifier is ported. A
    # token's mere presence is never treated as authentication.
    raise AppError(
        503,
        "INTERNAL_ERROR",
        "Supabase authentication is not available in this migration build.",
    )

