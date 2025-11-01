"""OpenAI-compatible LLM provider (vLLM, Ollama) with automatic fallback support."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field

from magsag.providers.base import LLMResponse

logger = logging.getLogger(__name__)


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
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    reasoning: dict[str, Any] | None = None


class ChatCompletionResponse(BaseModel):
    """Response from chat completion."""

    id: str
    model: str
    choices: list[dict[str, Any]]
    usage: dict[str, int] | None = None


class BaseOpenAICompatProvider(ABC):
    """Base class for OpenAI-compatible providers."""

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


class OpenAICompatProviderConfig(BaseModel):
    """Configuration for OpenAI-compatible provider."""

    base_url: str = Field(
        default="http://localhost:8000/v1/",
        description="Base URL for OpenAI-compatible API endpoint (must end with /)",
    )
    timeout: float = Field(
        default=3.0, description="Request timeout in seconds (reduced for fast failure)"
    )
    api_key: str | None = Field(
        default=None, description="API key (optional, some local servers require it)"
    )
    pricing: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Optional pricing table (per 1M tokens) used for cost estimation",
    )


class OpenAICompatProvider(BaseOpenAICompatProvider):
    """Provider for local LLM servers with OpenAI-compatible API (vLLM, Ollama).

    This provider connects to local LLM servers that expose OpenAI-compatible endpoints.
    When advanced features like structured responses or streaming are requested but not
    supported, it automatically falls back to standard chat completions with warnings.

    P1 Fixes Applied:
    - base_url must end with trailing slash to ensure relative paths join correctly
    - Uses relative path "chat/completions" which joins with base_url properly
    - Disables streaming support (supports_streaming=False) since implementation
      does not handle event-stream responses
    """

    def __init__(self, config: OpenAICompatProviderConfig | None = None) -> None:
        """Initialize OpenAI-compatible provider.

        Args:
            config: Provider configuration. If None, uses default configuration.
        """
        self.config = config or OpenAICompatProviderConfig()
        # Use fine-grained timeout: fail fast on connection, allow time for generation
        timeout = httpx.Timeout(
            connect=1.0,  # Fast failure if server is unavailable
            read=self.config.timeout,
            write=5.0,
            pool=5.0,
        )
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=timeout,
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
        but may not support advanced features like structured responses or streaming.
        """
        return ProviderCapabilities(
            supports_chat=True,
            supports_responses=False,  # Most local servers don't support this yet
            supports_streaming=False,  # Not implemented in this provider
            supports_function_calling=False,
        )

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Execute chat completion request with automatic fallback.

        If the request contains features not supported by the local provider
        (e.g., structured response_format or streaming), this method will:
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
        fallback_warnings: list[str] = []
        capabilities = self.get_capabilities()

        # Prepare request payload
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
        }

        if request.temperature is not None:
            payload["temperature"] = request.temperature

        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        # Check for streaming (not supported)
        if request.stream:
            if not capabilities.supports_streaming:
                fallback_warnings.append(
                    "Streaming is not supported by this provider. "
                    "Falling back to non-streaming chat completion."
                )
                # Don't include stream in the payload
            else:
                payload["stream"] = request.stream

        # Check for response_format (structured outputs)
        if request.response_format is not None:
            if not capabilities.supports_responses:
                fallback_warnings.append(
                    "response_format is not supported by this local provider. "
                    "Falling back to standard chat completion. "
                    "Consider adding format instructions to the system message instead."
                )
                # Don't include response_format in the payload
            else:
                payload["response_format"] = request.response_format

        # Check tool usage support
        if request.tools:
            if not capabilities.supports_function_calling:
                fallback_warnings.append(
                    "Tool calls are not supported by this provider. "
                    "Dropping tools and tool_choice parameters."
                )
            else:
                payload["tools"] = request.tools
                if request.tool_choice is not None:
                    payload["tool_choice"] = request.tool_choice
        elif request.tool_choice is not None:
            fallback_warnings.append(
                "tool_choice was provided without tools or function-call support. Ignoring value."
            )

        # Reasoning parameters are not supported by basic OpenAI-compatible endpoints
        if request.reasoning is not None:
            fallback_warnings.append(
                "Reasoning configuration is not supported by this provider. Ignoring `reasoning`."
            )

        # Log warnings if fallback is needed
        for warning in fallback_warnings:
            logger.warning(warning)

        # Execute request with relative path to respect base_url
        response = await self._client.post("chat/completions", json=payload)
        response.raise_for_status()

        # Parse and return response
        response_data = response.json()
        return ChatCompletionResponse(**response_data)

    async def close(self) -> None:
        """Clean up provider resources."""
        await self._client.aclose()

    async def __aenter__(self) -> "OpenAICompatProvider":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    def _run_chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Execute chat completion request from synchronous context."""

        async def _execute() -> ChatCompletionResponse:
            return await self.chat_completion(request)

        try:
            return asyncio.run(_execute())
        except RuntimeError as exc:
            # Handle nested event loops (e.g., notebooks) by creating a dedicated loop
            if "asyncio.run() cannot be called" not in str(exc):
                raise
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self.chat_completion(request))
            finally:
                loop.close()

    def generate(
        self,
        prompt: str,
        *,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str | dict[str, Any]] = None,
        response_format: Optional[dict[str, Any]] = None,
        reasoning: Optional[dict[str, Any]] = None,
        mcp_tools: Optional[list[dict[str, Any]]] = None,
        **_: Any,
    ) -> LLMResponse:
        """Synchronously generate a completion following BaseLLMProvider semantics."""
        capabilities = self.get_capabilities()
        sanitized_tools = tools
        sanitized_tool_choice = tool_choice
        sanitized_response_format = response_format
        warnings: list[str] = []

        if tools and not capabilities.supports_function_calling:
            warnings.append(
                "Tools were requested but this provider does not support function calling. Dropping tools."
            )
            sanitized_tools = None
            sanitized_tool_choice = None
        if tool_choice and not capabilities.supports_function_calling:
            warnings.append(
                "tool_choice was provided but function calling is unsupported. Dropping tool_choice."
            )
            sanitized_tool_choice = None
        if response_format and not capabilities.supports_responses:
            warnings.append(
                "Structured response_format is not supported by this provider. "
                "Output may not match the requested schema."
            )
            sanitized_response_format = None
        if reasoning is not None:
            warnings.append(
                "Reasoning configuration is not supported by this provider and will be ignored."
            )
        if mcp_tools:
            warnings.append(
                "MCP tool definitions are not supported by OpenAI-compatible providers."
            )

        for warning in warnings:
            logger.warning(warning)

        request = ChatCompletionRequest(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=sanitized_response_format,
            tools=sanitized_tools,
            tool_choice=sanitized_tool_choice,
        )

        response = self._run_chat_completion(request)
        llm_response = self._chat_response_to_llm_response(
            response,
            response_format_requested=response_format,
            warnings=warnings,
        )

        return llm_response

    def _chat_response_to_llm_response(
        self,
        response: ChatCompletionResponse,
        *,
        response_format_requested: Optional[dict[str, Any]],
        warnings: list[str],
    ) -> LLMResponse:
        """Convert a ChatCompletionResponse into an LLMResponse dataclass."""
        primary_choice = response.choices[0] if response.choices else {}
        message = primary_choice.get("message", {})
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls")
        usage = response.usage or {}
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cost_usd = self.get_cost(response.model, input_tokens, output_tokens)

        metadata: dict[str, Any] = {
            "id": response.id,
            "finish_reason": primary_choice.get("finish_reason"),
            "endpoint": "chat_completions",
            "raw_choices": response.choices,
            "cost_usd": cost_usd,
        }
        if warnings:
            metadata["warnings"] = warnings

        return LLMResponse(
            content=content,
            model=response.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_calls=tool_calls if tool_calls else None,
            response_format_ok=response_format_requested is None,
            raw_output_blocks=None,
            metadata=metadata,
        )

    def get_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estimate cost in USD based on configured pricing."""
        pricing = self.config.pricing.get(model)
        if not pricing:
            return 0.0

        prompt_rate = pricing.get("prompt", 0.0)
        completion_rate = pricing.get("completion", 0.0)
        return (input_tokens / 1_000_000) * prompt_rate + (
            output_tokens / 1_000_000
        ) * completion_rate
