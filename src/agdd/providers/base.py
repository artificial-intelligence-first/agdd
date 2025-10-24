"""Base provider interface for LLM integrations."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ProviderCapabilities(BaseModel):
    """Capabilities supported by a provider."""

    supports_chat: bool = True
    supports_responses: bool = False
    supports_streaming: bool = False
    supports_function_calling: bool = False


class ChatCompletionRequest(BaseModel):
    """Request for chat completion."""

    model: str
    messages: list[dict[str, Any]]
    temperature: float | None = None
    max_tokens: int | None = None
    response_format: dict[str, Any] | None = None
    stream: bool = False


class ChatCompletionResponse(BaseModel):
    """Response from chat completion."""

    id: str
    model: str
    choices: list[dict[str, Any]]
    usage: dict[str, int] | None = None


class BaseProvider(ABC):
    """Base class for LLM providers."""

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Get provider capabilities."""
        pass

    @abstractmethod
    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Execute chat completion request."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up provider resources."""
        pass
