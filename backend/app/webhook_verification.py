from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from app.errors import AppError

# Providers differ on the header name, so accept the common spellings rather
# than forcing one. The value may be bare hex or prefixed, e.g. `sha256=<hex>`.
SIGNATURE_HEADERS = ("x-cretona-signature", "x-webhook-signature", "x-signature")
TIMESTAMP_HEADERS = ("x-cretona-timestamp", "x-webhook-timestamp", "x-timestamp")

DEFAULT_TOLERANCE_SECONDS = 300

# One message for every rejection. Which check failed is a server-side detail;
# telling a caller whether the header was missing or merely wrong hands them a
# free oracle for probing.
REFUSED = "Webhook signature could not be verified."


def signing_payload(timestamp: str, body: bytes) -> bytes:
    """The bytes the signature actually covers.

    The timestamp is inside the MAC, so it cannot be edited to refresh a
    captured request: changing it invalidates the signature, and keeping it
    puts the request outside the tolerance window.
    """
    return f"{timestamp}.".encode() + body


def verify_hmac_webhook(
    *,
    headers: dict[str, str],
    body: bytes,
    secret: str,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify a timestamped HMAC-SHA256 signature over the raw body, or refuse.

    This route is public and unauthenticated by nature, so the signature is the
    only thing standing between a stranger and another user's project. It fails
    closed: with no secret configured nothing is accepted, because an
    unverifiable webhook is worth less than no webhook at all.

    HMAC proves authenticity, not freshness. Without a timestamp in the signed
    payload, anyone who observes one valid delivery can resend those exact
    bytes forever and the signature still checks out (T2-4). The timestamp
    narrows that to `tolerance_seconds`; it does not close it, so a replay
    inside the window is still accepted. Shutting that last gap needs a stored
    nonce, which needs a table — deliberately not built until a provider that
    sends one exists.
    """
    if not secret:
        raise AppError(401, "UNAUTHENTICATED", REFUSED)

    provided = _provided_signature(headers)
    if not provided:
        raise AppError(401, "UNAUTHENTICATED", REFUSED)

    timestamp = _provided_timestamp(headers)
    if timestamp is None:
        raise AppError(401, "UNAUTHENTICATED", REFUSED)
    if not _is_fresh(timestamp, tolerance_seconds, now):
        raise AppError(401, "UNAUTHENTICATED", REFUSED)

    # Computed over the exact bytes received. Re-serializing parsed JSON first
    # would let a caller alter whitespace or key order and keep the signature.
    expected = hmac.new(
        secret.encode("utf-8"), signing_payload(timestamp, body), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, provided):
        raise AppError(401, "UNAUTHENTICATED", REFUSED)

    return _payload(body)


def _provided_timestamp(headers: dict[str, str]) -> str | None:
    """The raw header value, unparsed.

    Returned as received because it is what gets signed: normalizing it here
    and signing the normalized form would reject a legitimate `0300` that the
    sender signed verbatim.
    """
    lowered = {key.lower(): value for key, value in headers.items()}
    for name in TIMESTAMP_HEADERS:
        raw = lowered.get(name)
        if raw and raw.strip():
            return raw.strip()
    return None


def _is_fresh(timestamp: str, tolerance_seconds: int, now: datetime | None) -> bool:
    """Unix seconds, within tolerance in either direction.

    Future-dated deliveries are refused as well as stale ones: a sender whose
    clock runs fast would otherwise mint requests valid long after capture.
    """
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    current = int((now or datetime.now(UTC)).timestamp())
    return abs(current - sent_at) <= tolerance_seconds


def _provided_signature(headers: dict[str, str]) -> str | None:
    lowered = {key.lower(): value for key, value in headers.items()}
    for name in SIGNATURE_HEADERS:
        raw = lowered.get(name)
        if not raw:
            continue
        # `sha256=<hex>` and a bare hex digest are both accepted.
        _, _, tail = raw.rpartition("=")
        return (tail or raw).strip()
    return None


def _payload(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError(400, "VALIDATION_ERROR", "Webhook body is not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise AppError(400, "VALIDATION_ERROR", "Webhook body must be a JSON object.")
    return parsed
