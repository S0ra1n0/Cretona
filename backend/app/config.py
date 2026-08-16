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
    database_backend: Literal["sqlite", "postgres"] = "sqlite"
    # Postgres/Supabase connection string. Kept secret: it carries a password.
    database_url: SecretStr = SecretStr("")
    max_generation_attempts: int = Field(default=3, ge=1, le=10)
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    generation_timeout_seconds: int = Field(default=600, ge=30, le=86400)
    # Shared secret for provider webhook signatures. Empty means the public
    # webhook route rejects everything, which is the safe default.
    webhook_secret: SecretStr = SecretStr("")
    thumbnails_enabled: bool = True
    # External binary, not a Python dependency. Absent means no thumbnail, not
    # a failed generation.
    ffmpeg_path: str = "ffmpeg"
    thumbnail_seek_seconds: float = Field(default=1.0, ge=0, le=60)
    poller_enabled: bool = True
    poll_interval_seconds: float = Field(default=5.0, gt=0, le=300)
    poll_batch_size: int = Field(default=20, ge=1, le=500)
    # Must exceed how long a batch takes, or a slow batch's rows are re-claimed
    # by another instance while this one is still working on them.
    poll_lease_seconds: int = Field(default=120, ge=5, le=3600)
    # Raw provider audit entries are useful for diagnosis but may contain user
    # prompts. Keep them only for the accepted 180-day contract and prune in
    # bounded batches so maintenance cannot monopolize the database.
    generation_log_retention_enabled: bool = True
    generation_log_retention_days: int = Field(default=180, ge=1, le=3650)
    generation_log_retention_interval_seconds: int = Field(default=86400, ge=60, le=604800)
    generation_log_retention_batch_size: int = Field(default=10000, ge=1, le=100000)
    rate_limit_enabled: bool = True
    rate_limit_default_per_min: int = Field(default=120, ge=1, le=10000)
    rate_limit_generation_per_min: int = Field(default=10, ge=1, le=1000)
    request_log_sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    generation_quota_limit: int = Field(default=10, ge=1, le=1000)
    generation_quota_window_hours: int = Field(default=24, ge=1, le=720)
    database_path: Path = BACKEND_ROOT / "data" / "cretona.db"
    media_dir: Path = BACKEND_ROOT / "assets"
    default_video_provider: Literal["mock", "cloud", "local", "fake", "real", "wan21"] = "mock"
    real_ai_api_key: SecretStr = SecretStr("")
    real_ai_endpoint: str = ""
    cloud_ai_api_key: SecretStr = SecretStr("")
    cloud_ai_endpoint: str = ""
    local_model_endpoint: str = "http://localhost:11434"

    # local keeps media on the filesystem for the credential-free profile;
    # supabase stores it in a bucket and hands out bounded signed URLs.
    storage_backend: Literal["local", "supabase"] = "local"
    supabase_url: str = ""
    supabase_service_role_key: SecretStr = SecretStr("")
    supabase_uploads_bucket: str = "uploads"
    supabase_videos_bucket: str = "videos"
    # Bounded by construction: a signed URL that never expires is a public one.
    signed_url_ttl_seconds: int = Field(default=3600, ge=60, le=604800)

    dev_user_id: str = "00000000-0000-4000-8000-000000000001"

    # Supabase identity. SecretStr keeps the value out of reprs and logs; it is
    # read only where a signature is verified.
    # HS256 is the legacy shared-secret scheme; ES256 is Supabase's current
    # default, where the project publishes public keys and this backend holds
    # no signing secret. Chosen by configuration, never inferred from a token.
    supabase_jwt_algorithm: Literal["HS256", "ES256"] = "HS256"
    # Defaults to the project's well-known endpoint when left blank.
    supabase_jwks_url: str = ""
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
    def require_supabase_storage_credentials(self) -> Settings:
        if self.storage_backend != "supabase":
            return self
        if not self.supabase_url:
            raise ValueError(
                "CRETONA_SUPABASE_URL is required when CRETONA_STORAGE_BACKEND=supabase."
            )
        if not self.supabase_service_role_key.get_secret_value():
            raise ValueError(
                "CRETONA_SUPABASE_SERVICE_ROLE_KEY is required when "
                "CRETONA_STORAGE_BACKEND=supabase."
            )
        return self

    @model_validator(mode="after")
    def require_database_url_for_postgres(self) -> Settings:
        if self.database_backend == "postgres" and not self.database_url.get_secret_value():
            raise ValueError(
                "CRETONA_DATABASE_URL is required when CRETONA_DATABASE_BACKEND=postgres."
            )
        return self

    @model_validator(mode="after")
    def require_supabase_jwt_secret(self) -> Settings:
        # Fail at startup rather than on every request, matching how the Express
        # reference validates SUPABASE_JWT_SECRET when it loads its environment.
        if self.auth_mode != "supabase":
            return self
        if self.supabase_jwt_algorithm == "HS256":
            if not self.supabase_jwt_secret.get_secret_value():
                raise ValueError(
                    "CRETONA_SUPABASE_JWT_SECRET is required when "
                    "CRETONA_SUPABASE_JWT_ALGORITHM=HS256."
                )
        elif not self.resolved_jwks_url():
            raise ValueError(
                "CRETONA_SUPABASE_URL or CRETONA_SUPABASE_JWKS_URL is required when "
                "CRETONA_SUPABASE_JWT_ALGORITHM=ES256."
            )
        return self

    def resolved_jwks_url(self) -> str:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return ""

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
