"""LLM provider abstractions and adapters for AGDD.

This module provides:
1. Base provider protocol (BaseLLMProvider, LLMResponse)
2. Adapters to translate OpenAI-compatible request formats to provider APIs
   - Anthropic Messages API with tools and streaming support
"""

from __future__ import annotations

from agdd.providers.base import BaseLLMProvider, LLMResponse

__all__ = ["BaseLLMProvider", "LLMResponse", "anthropic"]
