from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from app.errors import AppError

# Providers differ on the header name, so accept the common spellings rather
# than forcing one. The value may be bare hex or prefixed, e.g. `sha256=<hex>`.
SIGNATURE_HEADERS = ("x-cretona-signature", "x-webhook-signature", "x-signature")

# One message for every rejection. Which check failed is a server-side detail;
# telling a caller whether the header was missing or merely wrong hands them a
# free oracle for probing.
REFUSED = "Webhook signature could not be verified."


def verify_hmac_webhook(
    *,
    headers: dict[str, str],
    body: bytes,
    secret: str,
) -> dict[str, Any]:
    """Verify an HMAC-SHA256 signature over the raw body, or refuse.

    This route is public and unauthenticated by nature, so the signature is the
    only thing standing between a stranger and another user's project. It fails
    closed: with no secret configured nothing is accepted, because an
    unverifiable webhook is worth less than no webhook at all.
    """
    if not secret:
        raise AppError(401, "UNAUTHENTICATED", REFUSED)

    provided = _provided_signature(headers)
    if not provided:
        raise AppError(401, "UNAUTHENTICATED", REFUSED)

    # Computed over the exact bytes received. Re-serializing parsed JSON first
    # would let a caller alter whitespace or key order and keep the signature.
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, provided):
        raise AppError(401, "UNAUTHENTICATED", REFUSED)

    return _payload(body)


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
