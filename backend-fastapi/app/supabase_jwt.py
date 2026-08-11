from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

# Supabase's legacy signing uses HS256 with the project JWT secret (ADR-002).
# If a project is migrated to asymmetric signing keys, only this module changes:
# swap the shared secret for a JWKS lookup and widen the pinned algorithm.
EXPECTED_ALGORITHM = "HS256"


class TokenError(Exception):
    """A token that cannot be trusted.

    The specific reason stays server-side. Callers map every instance onto one
    opaque ``TOKEN_INVALID`` response so the API never becomes an oracle for
    which check failed.
    """


@dataclass(frozen=True)
class VerifiedIdentity:
    """The only facts a verified Supabase access token establishes.

    Identity comes from the token; authority (role, disabled state) is a
    database question and is deliberately not represented here.
    """

    user_id: str
    email: str | None


def verify_supabase_token(
    token: str,
    *,
    secret: str,
    audience: str | None = None,
    issuer: str | None = None,
    leeway_seconds: int = 0,
) -> VerifiedIdentity:
    """Verify a Supabase access token, or raise :class:`TokenError`."""
    if not secret:
        raise TokenError("No JWT secret is configured.")

    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("A JWS compact serialization has exactly three segments.")
    header_segment, payload_segment, signature_segment = parts

    header = _json_object(_b64url_decode(header_segment), "header")
    # The algorithm is pinned, never read from the token to choose a key. That
    # is what makes `alg: none` and RS256-to-HS256 confusion structurally
    # impossible here rather than merely unlikely.
    if header.get("alg") != EXPECTED_ALGORITHM:
        raise TokenError("Unsupported token algorithm.")

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        f"{header_segment}.{payload_segment}".encode(),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected_signature, _b64url_decode(signature_segment)):
        raise TokenError("Token signature does not match.")

    # Claims are read only after the signature proves they are ours.
    claims = _json_object(_b64url_decode(payload_segment), "payload")
    _reject_outside_time_window(claims, leeway_seconds)

    if issuer and claims.get("iss") != issuer:
        raise TokenError("Token issuer is not accepted.")
    if audience and not _audience_matches(claims.get("aud"), audience):
        raise TokenError("Token audience is not accepted.")

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise TokenError("Token carries no subject claim.")

    email = claims.get("email")
    return VerifiedIdentity(
        user_id=subject,
        email=email if isinstance(email, str) else None,
    )


def _reject_outside_time_window(claims: dict[str, Any], leeway_seconds: int) -> None:
    now = time.time()

    # A token with no expiry would never expire, so absence is a rejection
    # rather than a skipped check.
    expires_at = _as_timestamp(claims.get("exp"))
    if expires_at is None:
        raise TokenError("Token carries no usable expiry claim.")
    if now >= expires_at + leeway_seconds:
        raise TokenError("Token has expired.")

    not_before = _as_timestamp(claims.get("nbf"))
    if not_before is not None and now < not_before - leeway_seconds:
        raise TokenError("Token is not valid yet.")


def _audience_matches(claim: Any, expected: str) -> bool:
    if isinstance(claim, str):
        return claim == expected
    if isinstance(claim, list):
        return any(isinstance(item, str) and item == expected for item in claim)
    return False


def _as_timestamp(value: Any) -> float | None:
    # `bool` is a subclass of `int`; a JSON `true` is not a timestamp.
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(segment + padding)
    except (binascii.Error, ValueError) as exc:
        raise TokenError("Token segment is not valid base64url.") from exc


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TokenError(f"Token {label} is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise TokenError(f"Token {label} is not a JSON object.")
    return value
