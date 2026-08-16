from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request

from app.config import Settings
from app.errors import AppError
from app.supabase_jwt import (
    TokenError,
    VerifiedIdentity,
    verify_asymmetric_token,
    verify_supabase_token,
)

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
        user_id = _development_identity(x_debug_user_id, settings)
        # Roles still come from the database. A dev profile exercises the admin
        # surface by seeding a row, never by asserting a header.
        record = request.app.state.database.get_user(user_id)
        request.state.auth_role = (record or {}).get("role", "user")
        return user_id

    # Deployed profiles never consult X-Debug-User-Id. It is not read past this
    # branch, so a caller cannot assert an identity by sending the header.
    identity = _verified_identity(request, authorization, settings)
    request.state.auth_email = identity.email
    return _resolved_account(request, identity)


def _resolved_account(request: Request, identity: VerifiedIdentity) -> str:
    """Resolve the database row behind a verified token.

    A token proves identity; the database decides authority. Roles and disabled
    state are read here and never from a token claim the client could influence
    (SECURITY.md 2), mirroring the Express loadUser/rejectIfDisabled chain.
    """
    user = request.app.state.database.get_user(identity.user_id)

    if user is None:
        # The token verifies but no profile exists, so the signup trigger never
        # fired. Treat as unauthenticated rather than failing downstream.
        raise AppError(
            401,
            "TOKEN_INVALID",
            "Your account is not set up. Please sign in again.",
        )

    # Checked before any authorization so a disabled admin is stopped too
    # (FR-1.8, ARCHITECTURE.md 4.1).
    if user["is_disabled"]:
        raise AppError(403, "ACCOUNT_DISABLED", "This account has been disabled.")

    request.state.auth_role = user.get("role", "user")
    return identity.user_id


def require_admin(
    request: Request,
    user_id: Annotated[str, Depends(current_user_id)],
) -> str:
    """Role gate (P2-5).

    Runs after identity is established, so `auth_role` is already resolved from
    the database. Hiding a screen in the app is not authorization; this is
    (SECURITY.md 3).
    """
    if getattr(request.state, "auth_role", "user") != "admin":
        raise AppError(403, "FORBIDDEN", "You do not have access to this resource.")
    return user_id


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


def _verified_identity(
    request: Request,
    authorization: str | None,
    settings: Settings,
) -> VerifiedIdentity:
    token = _bearer_token(authorization)
    try:
        if settings.supabase_jwt_algorithm == "ES256":
            return verify_asymmetric_token(
                token,
                jwks=request.app.state.jwks,
                audience=settings.supabase_jwt_audience or None,
                issuer=settings.supabase_jwt_issuer or None,
                leeway_seconds=settings.supabase_jwt_leeway_seconds,
            )
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
