"""Unit tests for API configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from magsag.api.config import Settings


def test_default_settings() -> None:
    """Test default settings are valid."""
    settings = Settings()
    assert settings.CORS_ORIGINS == ["*"]
    assert settings.CORS_ALLOW_CREDENTIALS is False
    assert settings.API_DEBUG is False
    assert settings.API_PREFIX == "/api/v1"


def test_cors_credentials_with_wildcard_origins_fails() -> None:
    """Test that CORS_ALLOW_CREDENTIALS=True with wildcard origins raises error."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(CORS_ALLOW_CREDENTIALS=True, CORS_ORIGINS=["*"])

    assert "CORS_ALLOW_CREDENTIALS" in str(exc_info.value)


def test_cors_credentials_with_explicit_origins_succeeds() -> None:
    """Test that CORS_ALLOW_CREDENTIALS=True with explicit origins is valid."""
    settings = Settings(
        CORS_ALLOW_CREDENTIALS=True,
        CORS_ORIGINS=["https://example.com", "https://app.example.com"],
    )
    assert settings.CORS_ALLOW_CREDENTIALS is True
    assert settings.CORS_ORIGINS == ["https://example.com", "https://app.example.com"]


def test_cors_no_credentials_with_wildcard_succeeds() -> None:
    """Test that CORS_ALLOW_CREDENTIALS=False with wildcard origins is valid."""
    settings = Settings(CORS_ALLOW_CREDENTIALS=False, CORS_ORIGINS=["*"])
    assert settings.CORS_ALLOW_CREDENTIALS is False
    assert settings.CORS_ORIGINS == ["*"]
