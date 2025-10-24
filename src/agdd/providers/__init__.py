"""
LLM Provider implementations for AGDD.

This module contains provider implementations for various LLM services,
with support for standard and optimized API endpoints.
"""

from __future__ import annotations

# Core protocol (used by MAG/SAG)
from agdd.providers.base import BaseLLMProvider, LLMResponse

# Import submodules to make them available via package namespace
from . import openai

# OpenAI-compatible providers (vLLM, Ollama)
from agdd.providers.openai_compat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    OpenAICompatProvider,
    ProviderCapabilities,
)

__all__ = [
    # Core protocol
    "BaseLLMProvider",
    "LLMResponse",
    # OpenAI provider module
    "openai",
    # OpenAI-compatible providers (vLLM, Ollama)
    "OpenAICompatProvider",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ProviderCapabilities",
]
