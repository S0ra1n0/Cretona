from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_rejects_development_auth() -> None:
    with pytest.raises(ValidationError, match="forbidden in production"):
        Settings(environment="production", auth_mode="dev")


def test_production_accepts_fail_closed_supabase_mode() -> None:
    settings = Settings(environment="production", auth_mode="supabase")

    assert settings.auth_mode == "supabase"
