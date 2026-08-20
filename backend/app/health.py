from __future__ import annotations

import logging
from typing import Any

from app.errors import AppError

logger = logging.getLogger("cretona.health")


def require_database_connection(database: Any) -> None:
    """Fail a readiness check without exposing driver or credential details."""
    try:
        if hasattr(database, "connect"):
            with database.connect() as connection:
                connection.execute("SELECT 1").fetchone()
        elif hasattr(database, "pool"):
            with database.pool.connection() as connection:
                connection.execute("SELECT 1").fetchone()
    except Exception as error:
        logger.error("database_health_check_failed", exc_info=error)
        raise AppError(
            503,
            "SERVICE_UNAVAILABLE",
            "Database connectivity check failed.",
        ) from error
