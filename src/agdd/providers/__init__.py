"""LLM provider abstractions for AGDD."""

# Core protocol (used by MAG/SAG)
from agdd.providers.base import BaseLLMProvider, LLMResponse

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
    # OpenAI-compatible
    "OpenAICompatProvider",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ProviderCapabilities",
]
