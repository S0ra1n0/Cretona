from __future__ import annotations

from typing import Any

from app.errors import AppError
from app.quota_service import QuotaService
from app.repository import UsernameTakenError
from app.schemas import MeResponse


class UsersService:
    def __init__(self, database: Any, quota: QuotaService) -> None:
        self.database = database
        self.quota = quota

    def get_me(self, user_id: str) -> MeResponse:
        row = self.database.get_user(user_id)
        if row is None:
            raise AppError(404, "NOT_FOUND", "User not found.")
        return self._to_response(row, user_id)

    def update_me(self, user_id: str, username: str) -> MeResponse:
        try:
            row = self.database.set_username(user_id, username)
        except UsernameTakenError as exc:
            # Checking availability before writing would still race; letting
            # the unique index decide and translating it is the only correct
            # version.
            raise AppError(409, "CONFLICT", "That username is already taken.") from exc

        if row is None:
            raise AppError(404, "NOT_FOUND", "User not found.")
        return self._to_response(row, user_id)

    def _to_response(self, row: dict[str, Any], user_id: str) -> MeResponse:
        return MeResponse(
            id=row["id"],
            email=row.get("email"),
            username=row.get("username"),
            role=row.get("role", "user"),
            isDisabled=bool(row.get("is_disabled")),
            createdAt=row.get("created_at") or "",
            quota=self.quota.get(user_id),
        )
