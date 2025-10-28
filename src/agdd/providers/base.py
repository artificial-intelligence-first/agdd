"""LLM provider abstraction for AGDD."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass
class BaseProviderConfig:
    """Base configuration for LLM providers with common functionality."""

    api_key: Optional[str] = None
    """API key for the provider. If None, will be read from environment."""

    timeout: float = 60.0
    """Request timeout in seconds."""

    max_retries: int = 2
    """Maximum number of retries for failed requests."""

    def get_api_key(self, env_var: str) -> str:
        """
        Get API key from config or environment variable.

        Args:
            env_var: Name of the environment variable to check

        Returns:
            API key string

        Raises:
            ValueError: If API key not found in config or environment
        """
        if self.api_key:
            return self.api_key
        key = os.getenv(env_var)
        if not key:
            raise ValueError(f"{env_var} not found in config or environment")
        return key


@dataclass(slots=True)
class LLMResponse:
    """Response from an LLM provider."""

    content: str
    """The main text content of the response."""

    model: str
    """The model identifier used for this completion."""

    input_tokens: int
    """Number of tokens in the input/prompt."""

    output_tokens: int
    """Number of tokens in the output/completion."""

    tool_calls: Optional[list[dict[str, Any]]] = None
    """Tool/function calls requested by the model, if any."""

    response_format_ok: bool = True
    """Whether the response conformed to the requested format."""

    raw_output_blocks: Optional[list[dict[str, Any]]] = None
    """Raw output blocks from the provider (e.g., for structured outputs)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional provider-specific metadata."""


class BaseLLMProvider(Protocol):
    """Protocol describing the LLM provider surface expected by AGDD."""

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
        **kwargs: Any,
    ) -> LLMResponse:  # pragma: no cover - interface contract
        """Generate a completion from the LLM.

        Args:
            prompt: The input prompt/message.
            model: The model identifier to use.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (0.0-2.0).
            tools: Tool definitions for function calling.
            tool_choice: Strategy for tool selection (e.g., "auto", "required", specific tool).
            response_format: Desired response format (e.g., JSON schema).
            reasoning: Reasoning configuration (e.g., extended thinking mode).
            mcp_tools: MCP (Model Context Protocol) tool definitions.
            **kwargs: Additional provider-specific parameters.

        Returns:
            LLMResponse containing the completion and metadata.
        """

    def get_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:  # pragma: no cover - interface contract
        """Calculate the cost for a completion.

        Args:
            model: The model identifier.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.

        Returns:
            Cost in USD.
        """
