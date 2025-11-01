"""
LLM Provider implementations for MAGSAG.

This module contains provider implementations for various LLM services,
with support for standard and optimized API endpoints.
"""

from __future__ import annotations

# Core protocol (used by MAG/SAG)
from magsag.providers.base import BaseLLMProvider, LLMResponse
from magsag.providers.google import GoogleProvider
from magsag.providers.local import LocalLLMProvider, LocalProviderConfig
from magsag.providers.mock import MockLLMProvider

# Import submodules to make them available via package namespace
from . import anthropic, openai

# OpenAI-compatible providers (vLLM, Ollama)
from magsag.providers.openai_compat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    OpenAICompatProvider,
    OpenAICompatProviderConfig,
    ProviderCapabilities,
)

__all__ = [
    # Core protocol
    "BaseLLMProvider",
    "LLMResponse",
    # Google provider
    "GoogleProvider",
    # Local provider
    "LocalLLMProvider",
    "LocalProviderConfig",
    # Mock provider (for testing)
    "MockLLMProvider",
    # Provider modules
    "anthropic",
    "openai",
    # OpenAI-compatible providers (vLLM, Ollama)
    "OpenAICompatProvider",
    "OpenAICompatProviderConfig",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ProviderCapabilities",
]
