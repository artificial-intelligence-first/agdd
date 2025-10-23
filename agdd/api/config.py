"""API configuration management."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """API server settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_prefix="AGDD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API configuration
    API_DEBUG: bool = Field(default=False, description="Enable debug mode")
    API_PREFIX: str = Field(default="/api/v1", description="API route prefix")
    API_HOST: str = Field(default="0.0.0.0", description="API server host")
    API_PORT: int = Field(default=8000, description="API server port")

    # Authentication
    API_KEY: str | None = Field(default=None, description="API key for authentication (optional)")

    # CORS
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["*"], description="Allowed CORS origins"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=False,
        description="Allow credentials (cookies, authorization headers) in CORS requests. "
        "Cannot be True when CORS_ORIGINS includes '*'.",
    )

    # Observability (Legacy file-based)
    RUNS_BASE_DIR: str = Field(
        default=".runs/agents", description="Base directory for agent run artifacts (legacy)"
    )

    # Storage (New unified storage layer)
    STORAGE_BACKEND: str = Field(
        default="sqlite", description="Storage backend: sqlite, postgres, timescale"
    )
    STORAGE_DB_PATH: str = Field(
        default=".agdd/storage.db", description="SQLite database path (sqlite backend only)"
    )
    STORAGE_ENABLE_FTS: bool = Field(
        default=True, description="Enable FTS5 full-text search (sqlite backend only)"
    )
    STORAGE_DSN: str | None = Field(
        default=None, description="Database connection string (postgres/timescale backends)"
    )

    # Data lifecycle
    STORAGE_HOT_DAYS: int = Field(
        default=7, description="Keep data in hot storage for this many days"
    )
    STORAGE_ARCHIVE_ENABLED: bool = Field(
        default=False, description="Enable automatic archival to cold storage"
    )
    STORAGE_ARCHIVE_DESTINATION: str | None = Field(
        default=None, description="Archive destination URI (e.g., s3://bucket/prefix)"
    )

    # Rate limiting
    RATE_LIMIT_QPS: int | None = Field(
        default=None, description="Rate limit in queries per second (optional)"
    )
    REDIS_URL: str | None = Field(
        default=None, description="Redis URL for distributed rate limiting (optional)"
    )

    # GitHub integration
    GITHUB_WEBHOOK_SECRET: str | None = Field(
        default=None, description="GitHub webhook secret for signature verification (optional)"
    )
    GITHUB_TOKEN: str | None = Field(
        default=None, description="GitHub token for posting comments (optional)"
    )

    @model_validator(mode="after")
    def validate_cors_credentials(self) -> "Settings":
        """Validate that CORS credentials are not enabled with wildcard origins."""
        if self.CORS_ALLOW_CREDENTIALS and "*" in self.CORS_ORIGINS:
            raise ValueError(
                "Cannot set CORS_ALLOW_CREDENTIALS=True when CORS_ORIGINS includes '*'. "
                "Either set CORS_ALLOW_CREDENTIALS=False or specify explicit origins."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
