"""
LLM Provider implementations for AGDD.

This module contains provider implementations for various LLM services,
with support for standard and optimized API endpoints.
"""

from __future__ import annotations

# Core protocol (used by MAG/SAG)
from agdd.providers.base import BaseLLMProvider, LLMResponse
from agdd.providers.google import GoogleProvider
from agdd.providers.local import LocalLLMProvider, LocalProviderConfig

# Import submodules to make them available via package namespace
from . import anthropic, openai

# OpenAI-compatible providers (vLLM, Ollama)
from agdd.providers.openai_compat import (
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
