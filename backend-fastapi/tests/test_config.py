from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_rejects_development_auth() -> None:
    with pytest.raises(ValidationError, match="forbidden in production"):
        Settings(environment="production", auth_mode="dev")


def test_production_accepts_verified_supabase_mode() -> None:
    settings = Settings(
        environment="production",
        auth_mode="supabase",
        supabase_jwt_secret="a-configured-signing-secret",
    )

    assert settings.auth_mode == "supabase"


def test_supabase_mode_requires_a_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="CRETONA_SUPABASE_JWT_SECRET is required"):
        Settings(environment="production", auth_mode="supabase")


def test_jwt_secret_is_not_exposed_by_repr() -> None:
    settings = Settings(auth_mode="supabase", supabase_jwt_secret="super-secret-value")

    assert "super-secret-value" not in repr(settings)
    assert settings.supabase_jwt_secret.get_secret_value() == "super-secret-value"
