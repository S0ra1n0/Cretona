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


def test_supabase_mode_requires_a_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CRETONA_SUPABASE_JWT_SECRET", raising=False)
    with pytest.raises(ValidationError, match="CRETONA_SUPABASE_JWT_SECRET is required"):
        Settings(_env_file=None, environment="production", auth_mode="supabase")


def test_jwt_secret_is_not_exposed_by_repr() -> None:
    settings = Settings(auth_mode="supabase", supabase_jwt_secret="super-secret-value")

    assert "super-secret-value" not in repr(settings)
    assert settings.supabase_jwt_secret.get_secret_value() == "super-secret-value"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("generation_log_retention_days", 0),
        ("generation_log_retention_interval_seconds", 59),
        ("generation_log_retention_batch_size", 0),
    ],
)
def test_generation_log_retention_rejects_unsafe_bounds(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_generation_log_retention_defaults_to_the_data_contract() -> None:
    settings = Settings()

    assert settings.generation_log_retention_enabled is True
    assert settings.generation_log_retention_days == 180
    assert settings.generation_log_retention_interval_seconds == 86400
    assert settings.generation_log_retention_batch_size == 10000


def test_third_party_image_endpoint_is_opt_in() -> None:
    settings = Settings(_env_file=None)

    assert settings.image_endpoint == ""


@pytest.mark.parametrize("provider", ["kaggle", "external"])
def test_external_worker_can_be_the_default_provider(provider: str) -> None:
    assert Settings(default_video_provider=provider).default_video_provider == provider
