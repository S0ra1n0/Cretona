from __future__ import annotations

from app.errors import AppError

# The project state machine (DATA_MODEL.md 2.3), ported from the Express
# reference at backend/src/services/projects/transitions.ts.
#
#   pending   -> generating -> completed | failed
#   failed    -> pending                   (retry, FR-2.11)
#
# This is the only definition of what is legal. Everything that writes `status`
# goes through assert_transition, so an illegal move is impossible to express
# rather than merely discouraged.
ALLOWED: dict[str, frozenset[str]] = {
    "pending": frozenset({"generating", "failed"}),
    "generating": frozenset({"completed", "failed"}),
    "completed": frozenset(),
    "failed": frozenset({"pending"}),
}

TERMINAL = frozenset({"completed", "failed"})
IN_FLIGHT = frozenset({"pending", "generating"})

# A request the provider rejected on its merits will be rejected again, so
# retrying only burns quota (AI_PROVIDER_SPEC.md 2.1).
RETRYABLE_FAILURES = frozenset({"provider_error", "timeout", "quota", "unknown"})


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in ALLOWED.get(from_status, frozenset())


def assert_transition(from_status: str, to_status: str) -> None:
    if not can_transition(from_status, to_status):
        raise AppError(
            409,
            "CONFLICT",
            f"A {from_status} project cannot become {to_status}.",
        )


def is_retryable(error_code: str | None) -> bool:
    return error_code in RETRYABLE_FAILURES if error_code else False
