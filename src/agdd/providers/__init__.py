"""LLM provider adapters for AGDD framework.

This module provides adapters to translate OpenAI-compatible request formats
to various LLM provider APIs (Anthropic, etc.) with support for:
- Message format conversion
- Tool/function calling
- Streaming responses
"""

from __future__ import annotations

__all__ = ["anthropic"]
