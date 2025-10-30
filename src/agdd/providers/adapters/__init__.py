"""Provider SPI adapters for AGDD.

This package contains adapters that wrap existing provider implementations
to conform to the Provider SPI protocol.
"""

from __future__ import annotations

__all__ = [
    "OpenAIAdapter",
    "AnthropicAdapter",
    "GoogleAdapter",
]

# Import adapters (lazy import to avoid dependency issues)
try:
    from agdd.providers.adapters.openai_adapter import OpenAIAdapter
except ImportError:
    OpenAIAdapter = None  # type: ignore

try:
    from agdd.providers.adapters.anthropic_adapter import AnthropicAdapter
except ImportError:
    AnthropicAdapter = None  # type: ignore

try:
    from agdd.providers.adapters.google_adapter import GoogleAdapter
except ImportError:
    GoogleAdapter = None  # type: ignore
