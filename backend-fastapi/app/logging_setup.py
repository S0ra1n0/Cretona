from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

REDACTED = "[redacted]"

# Redaction lives here rather than at call sites, so no code path can leak a
# credential by forgetting to sanitise (SECURITY.md 6). Adding a field that
# carries a secret means adding it to this set, and nothing else.
#
# Matching is on the normalized key name, so `apiKey`, `api_key`, and
# `API-KEY` are all caught by one entry.
SENSITIVE_KEYS = frozenset(
    {
        "accesstoken",
        "apikey",
        "authorization",
        "cookie",
        "databaseurl",
        "encryptedpassword",
        "idempotencykey",
        "jwtsecret",
        "password",
        "secret",
        "servicerolekey",
        "setcookie",
        "signedurl",
        "token",
        "uploadurl",
    }
)

# Anything a LogRecord always carries. Everything else was passed by us as
# `extra=` and belongs in the structured payload.
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


def _normalize(key: str) -> str:
    return key.replace("_", "").replace("-", "").lower()


def redact(value: Any) -> Any:
    """Recursively censor secret-bearing keys in a structure."""
    if isinstance(value, Mapping):
        return {
            key: REDACTED if _normalize(str(key)) in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    # str and bytes are Sequences; they are values, not containers to walk.
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """Newline-delimited JSON so a host platform can parse it."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)

        # Redacting the assembled payload, rather than each field as it is
        # added, means a future field is covered without a code change here.
        return json.dumps(redact(payload), default=str)


class RedactingFilter(logging.Filter):
    """Second line of defence for records this app did not format itself."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(record.__dict__):
            if key in _RESERVED or key.startswith("_"):
                continue
            if _normalize(key) in SENSITIVE_KEYS:
                record.__dict__[key] = REDACTED
            else:
                record.__dict__[key] = redact(record.__dict__[key])
        return True


class StdoutHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Resolves sys.stdout at emit time rather than binding it once.

    A handler that captures the stream at construction keeps writing to
    whatever stdout was when the app was built, which makes it invisible to
    anything that legitimately replaces the stream afterwards.
    """

    def __init__(self) -> None:
        super().__init__(sys.stdout)

    @property
    def stream(self):  # type: ignore[override]
        return sys.stdout

    @stream.setter
    def stream(self, _value: object) -> None:
        # StreamHandler.__init__ assigns here; stay dynamic instead.
        return


def configure_logging(level: str = "info") -> logging.Logger:
    """Install the structured handler. Safe to call repeatedly."""
    handler = StdoutHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())

    root = logging.getLogger("cretona")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Ours is the only handler that redacts, so records must not also travel to
    # an ancestor logger that might print them raw.
    root.propagate = False
    return root
