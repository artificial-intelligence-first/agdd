"""Local LLM provider with OpenAI-compatible API support (vLLM, Ollama)."""

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

from agdd.providers.base import (
    BaseProvider,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ProviderCapabilities,
)

logger = logging.getLogger(__name__)


class LocalProviderConfig(BaseModel):
    """Configuration for local provider."""

    base_url: str = Field(
        default="http://localhost:8000/v1",
        description="Base URL for OpenAI-compatible API endpoint",
    )
    timeout: float = Field(default=60.0, description="Request timeout in seconds")
    api_key: str | None = Field(
        default=None, description="API key (optional, some local servers require it)"
    )


class LocalProvider(BaseProvider):
    """Provider for local LLM servers with OpenAI-compatible API (vLLM, Ollama).

    This provider connects to local LLM servers that expose OpenAI-compatible endpoints.
    When advanced features like structured responses are requested but not supported,
    it automatically falls back to standard chat completions with appropriate warnings.
    """

    def __init__(self, config: LocalProviderConfig | None = None) -> None:
        """Initialize local provider.

        Args:
            config: Provider configuration. If None, uses default configuration.
        """
        self.config = config or LocalProviderConfig()
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            headers=self._build_headers(),
        )

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers for requests."""
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def get_capabilities(self) -> ProviderCapabilities:
        """Get provider capabilities.

        Local providers (vLLM, Ollama) typically support basic chat completions
        but may not support advanced features like structured responses.
        """
        return ProviderCapabilities(
            supports_chat=True,
            supports_responses=False,  # Most local servers don't support this yet
            supports_streaming=True,
            supports_function_calling=False,
        )

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Execute chat completion request with automatic fallback.

        If the request contains features not supported by the local provider
        (e.g., structured response_format), this method will:
        1. Log a warning about the unsupported feature
        2. Strip the unsupported parameters
        3. Execute a standard chat completion
        4. Return the result

        Args:
            request: Chat completion request

        Returns:
            Chat completion response

        Raises:
            httpx.HTTPError: If the request fails
        """
        # Check for unsupported features and prepare fallback
        needs_fallback = False
        fallback_warnings: list[str] = []

        # Prepare request payload
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
        }

        if request.temperature is not None:
            payload["temperature"] = request.temperature

        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        if request.stream:
            payload["stream"] = request.stream

        # Check for response_format (structured outputs)
        if request.response_format is not None:
            capabilities = self.get_capabilities()
            if not capabilities.supports_responses:
                needs_fallback = True
                fallback_warnings.append(
                    "response_format is not supported by this local provider. "
                    "Falling back to standard chat completion. "
                    "Consider adding format instructions to the system message instead."
                )
                # Don't include response_format in the payload
            else:
                payload["response_format"] = request.response_format

        # Log warnings if fallback is needed
        if needs_fallback:
            for warning in fallback_warnings:
                logger.warning(warning)

        # Execute request
        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()

        # Parse and return response
        response_data = response.json()
        return ChatCompletionResponse(**response_data)

    async def close(self) -> None:
        """Clean up provider resources."""
        await self._client.aclose()

    async def __aenter__(self) -> "LocalProvider":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
