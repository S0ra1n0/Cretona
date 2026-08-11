from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Validated configuration loaded only on the server."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_prefix="CRETONA_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    auth_mode: Literal["dev", "supabase"] = "dev"
    database_path: Path = BACKEND_ROOT / "data" / "cretona.db"
    media_dir: Path = BACKEND_ROOT / "assets"
    default_video_provider: Literal["fake"] = "fake"

    dev_user_id: str = "00000000-0000-4000-8000-000000000001"

    # Supabase identity. SecretStr keeps the value out of reprs and logs; it is
    # read only where a signature is verified.
    supabase_jwt_secret: SecretStr = SecretStr("")
    supabase_jwt_audience: str = "authenticated"
    # Optional; enforced only when set, e.g. https://<ref>.supabase.co/auth/v1.
    supabase_jwt_issuer: str = ""
    supabase_jwt_leeway_seconds: int = Field(default=0, ge=0, le=120)

    prompt_llm_provider: Literal["deterministic", "ollama"] = "deterministic"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b-instruct-2507-q4_K_M"
    ollama_timeout_seconds: float = Field(default=45.0, gt=0, le=300)
    ollama_num_ctx: int = Field(default=4096, ge=512, le=32768)
    ollama_num_predict: int = Field(default=180, ge=32, le=1000)
    ollama_temperature: float = Field(default=0.2, ge=0, le=2)

    fake_polls_before_complete: int = Field(default=1, ge=1, le=20)
    fake_video_filename: str = "demo-output.mp4"

    @model_validator(mode="after")
    def reject_development_auth_in_production(self) -> Settings:
        if self.environment == "production" and self.auth_mode == "dev":
            raise ValueError("CRETONA_AUTH_MODE=dev is forbidden in production.")
        return self

    @model_validator(mode="after")
    def require_supabase_jwt_secret(self) -> Settings:
        # Fail at startup rather than on every request, matching how the Express
        # reference validates SUPABASE_JWT_SECRET when it loads its environment.
        if self.auth_mode == "supabase" and not self.supabase_jwt_secret.get_secret_value():
            raise ValueError(
                "CRETONA_SUPABASE_JWT_SECRET is required when CRETONA_AUTH_MODE=supabase."
            )
        return self

    def resolved_database_path(self) -> Path:
        return self._resolve_from_backend(self.database_path)

    def resolved_media_dir(self) -> Path:
        return self._resolve_from_backend(self.media_dir)

    @staticmethod
    def _resolve_from_backend(path: Path) -> Path:
        return path if path.is_absolute() else BACKEND_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
