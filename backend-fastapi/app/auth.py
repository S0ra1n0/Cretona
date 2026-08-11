from __future__ import annotations

from uuid import UUID

from fastapi import Header, Request

from app.config import Settings
from app.errors import AppError
from app.supabase_jwt import TokenError, VerifiedIdentity, verify_supabase_token

# One message for every rejected token. Which check failed is a server-side
# detail; API_CONTRACT.md §1.2 tells the app to refresh once, then sign out.
TOKEN_INVALID_MESSAGE = "Your session has expired. Please sign in again."


def current_user_id(
    request: Request,
    x_debug_user_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> str:
    settings: Settings = request.app.state.settings

    if settings.auth_mode == "dev":
        return _development_identity(x_debug_user_id, settings)

    # Deployed profiles never consult X-Debug-User-Id. It is not read past this
    # branch, so a caller cannot assert an identity by sending the header.
    identity = _verified_identity(authorization, settings)
    request.state.auth_email = identity.email
    return identity.user_id


def _development_identity(x_debug_user_id: str | None, settings: Settings) -> str:
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


def _verified_identity(authorization: str | None, settings: Settings) -> VerifiedIdentity:
    token = _bearer_token(authorization)
    try:
        return verify_supabase_token(
            token,
            secret=settings.supabase_jwt_secret.get_secret_value(),
            audience=settings.supabase_jwt_audience or None,
            issuer=settings.supabase_jwt_issuer or None,
            leeway_seconds=settings.supabase_jwt_leeway_seconds,
        )
    except TokenError as exc:
        raise AppError(401, "TOKEN_INVALID", TOKEN_INVALID_MESSAGE) from exc


def _bearer_token(authorization: str | None) -> str:
    """Extract the credential, or fail with UNAUTHENTICATED.

    A missing or malformed header is 401 UNAUTHENTICATED; a present but
    unusable token is 401 TOKEN_INVALID (API_CONTRACT.md §1.2).
    """
    if not authorization:
        raise AppError(401, "UNAUTHENTICATED", "Missing Authorization header.")

    scheme, _, credential = authorization.partition(" ")
    token = credential.strip()
    if scheme.lower() != "bearer" or not token:
        raise AppError(
            401,
            "UNAUTHENTICATED",
            'Authorization header must be "Bearer <token>".',
        )
    return token
