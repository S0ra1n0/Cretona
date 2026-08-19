from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Annotated, Any
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
        user = _provision_local_account(request, identity)

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

    # The signup trigger writes `email` once and never revisits it, so the row
    # kept whatever it was created or seeded with and every profile screen
    # showed that instead of the account's real address. The verified token is
    # the authority on the email; role and disabled state are emphatically not
    # (SECURITY.md 2) and are still read from the row above.
    if identity.email and identity.email != user.get("email"):
        _sync_email(request, identity.user_id, identity.email)

    request.state.auth_role = user.get("role", "user")
    return identity.user_id


def _provision_local_account(
    request: Request,
    identity: VerifiedIdentity,
) -> dict[str, Any] | None:
    """Create the missing row behind a verified token, on sqlite only.

    In a deployed profile the Supabase signup trigger owns this table, so a
    missing row means something is genuinely wrong and the caller still gets
    401. The local sqlite mirror has no trigger: nothing there ever learns
    about an account created through the app, so signing in with a real token
    hit "your account is not set up" forever and only the three seeded ids
    could get in.

    The row is created with no username, which is what puts a fresh account
    into profile setup, and with the default role -- authority is never taken
    from a token claim (SECURITY.md 2).
    """
    settings: Settings = request.app.state.settings
    if settings.database_backend != "sqlite":
        return None

    database = request.app.state.database
    if not hasattr(database, "upsert_user"):
        return None

    with contextlib.suppress(Exception):
        database.upsert_user(
            identity.user_id,
            email=identity.email,
            username=None,
            role="user",
            created_at=datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        )
        return database.get_user(identity.user_id)
    return None


def _sync_email(request: Request, user_id: str, email: str) -> None:
    """Best-effort write-through of the token's email claim.

    A failure here must not fail the request: the caller is authenticated
    either way, and a stale email is a display problem, not an access one.
    """
    database = request.app.state.database
    syncer = getattr(database, "sync_user_email", None)
    if syncer is None:
        return
    with contextlib.suppress(Exception):
        syncer(user_id, email)


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
