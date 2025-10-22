"""API configuration management."""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field
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

    # Observability
    RUNS_BASE_DIR: str = Field(
        default=".runs/agents", description="Base directory for agent run artifacts"
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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
