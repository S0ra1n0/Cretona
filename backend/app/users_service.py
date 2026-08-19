from __future__ import annotations

from typing import Any

from app.errors import AppError
from app.quota_service import QuotaService
from app.repository import UsernameTakenError
from app.schemas import MeResponse
from app.storage import assert_owns_path


class UsersService:
    def __init__(self, database: Any, quota: QuotaService, storage: Any = None) -> None:
        self.database = database
        self.quota = quota
        # Optional so existing callers and tests keep working; without it
        # the avatar simply has no URL rather than the request failing.
        self.storage = storage

    def get_me(self, user_id: str, base_url: str = "") -> MeResponse:
        row = self.database.get_user(user_id)
        if row is None:
            raise AppError(404, "NOT_FOUND", "User not found.")
        return self._to_response(row, user_id, base_url)

    def update_me(
        self,
        user_id: str,
        username: str | None,
        *,
        avatar_path: str | None = None,
        set_avatar: bool = False,
        gender: str | None = None,
        set_gender: bool = False,
        birthday: str | None = None,
        set_birthday: bool = False,
        base_url: str = "",
    ) -> MeResponse:
        if set_avatar and avatar_path:
            # The key embeds the owner as its first segment, so this is what
            # stops one account pointing its avatar at another's upload.
            assert_owns_path(user_id, avatar_path)

        try:
            row = self.database.update_profile(
                user_id,
                username=username,
                avatar_path=avatar_path,
                set_avatar=set_avatar,
                gender=gender,
                set_gender=set_gender,
                birthday=birthday,
                set_birthday=set_birthday,
            )
        except UsernameTakenError as exc:
            # Checking availability before writing would still race; letting
            # the unique index decide and translating it is the only correct
            # version.
            raise AppError(409, "CONFLICT", "That username is already taken.") from exc

        if row is None:
            raise AppError(404, "NOT_FOUND", "User not found.")
        return self._to_response(row, user_id, base_url)

    def _to_response(self, row: dict[str, Any], user_id: str, base_url: str = "") -> MeResponse:
        avatar_path = row.get("avatar_path")
        avatar_url = None
        if avatar_path and self.storage is not None:
            # video=False selects the uploads bucket, where avatars live.
            avatar_url = self.storage.read_url(avatar_path, base_url, video=False)

        return MeResponse(
            id=row["id"],
            email=row.get("email"),
            username=row.get("username"),
            avatarUrl=avatar_url,
            gender=row.get("gender"),
            birthday=row.get("birthday"),
            role=row.get("role", "user"),
            isDisabled=bool(row.get("is_disabled")),
            createdAt=row.get("created_at") or "",
            quota=self.quota.get(user_id),
        )
