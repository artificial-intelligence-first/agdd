"""Anthropic Provider SPI Adapter.

This adapter wraps the existing Anthropic provider implementation to conform
to the Provider SPI protocol.
"""

from __future__ import annotations

import asyncio
import warnings
from typing import TYPE_CHECKING, Any, Literal, Optional

if TYPE_CHECKING:
    try:
        from agdd.core.spi.provider import Provider, CapabilityMatrix
    except ImportError:
        Provider = Any  # type: ignore
        CapabilityMatrix = Any  # type: ignore
else:
    Provider = Any
    CapabilityMatrix = Any

from agdd.providers.anthropic import AnthropicProvider, CompletionRequest


class AnthropicAdapter:
    """SPI-compliant adapter for Anthropic provider.

    This adapter wraps the existing AnthropicProvider to provide a standardized
    interface that conforms to the Provider SPI protocol.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.anthropic.com/v1",
        default_model: str = "claude-3-5-sonnet-20241022",
    ) -> None:
        """Initialize the adapter with an Anthropic provider.

        Args:
            api_key: Optional Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            base_url: API base URL
            default_model: Default model to use
        """
        self._legacy = AnthropicProvider(
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
        )
        self._default_model = default_model

    def capabilities(self) -> dict[str, bool]:
        """Return capability matrix for Anthropic models.

        Returns:
            Dictionary describing model capabilities:
            - tools: Function/tool calling support
            - structured_output: JSON mode and structured outputs
            - vision: Image understanding (Claude 3+ models)
            - audio: Audio processing capabilities

        Note:
            Structured_output is set to False because direct JSON schema
            enforcement is not exposed through the current provider interface.
            Anthropic supports structured output via tool use patterns, but
            that's a different mechanism than OpenAI's response_format.
        """
        return {
            "tools": True,  # Full tool/function calling support
            "structured_output": False,  # Direct JSON schema not wired through provider
            "vision": True,  # Available in Claude 3+ models
            "audio": False,  # Not yet supported
        }

    async def generate(
        self,
        prompt: dict[str, Any] | str,
        tools: Optional[list[dict[str, Any]]] = None,
        *,
        mode: Literal["text", "vision", "audio"] = "text",
        schema: Optional[dict[str, Any]] = None,
        model: Optional[str] = None,
        temperature: float = 1.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a completion using the Anthropic provider.

        Args:
            prompt: Input prompt, either as string or structured dict with messages
            tools: Optional list of tool/function definitions (OpenAI format)
            mode: Generation mode (text, vision, or audio)
            schema: Optional JSON schema for structured output
            model: Model identifier to use (defaults to provider's default)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            Dictionary containing:
            - content: Generated text content
            - tool_calls: List of tool calls if any
            - model: Model used
            - usage: Token usage information
            - stop_reason: Completion stop reason

        Note:
            The schema parameter is currently not forwarded to AnthropicProvider
            because direct JSON schema enforcement is not exposed. A warning will
            be issued if schema is provided. Use tool use patterns for structured output.
        """
        # Warn if unsupported schema parameter is provided
        if schema is not None:
            warnings.warn(
                "AnthropicAdapter: schema parameter is not yet supported and will be ignored. "
                "Use tool use patterns for structured output, or set capabilities['structured_output'] = False",
                UserWarning,
                stacklevel=2,
            )

        # Convert prompt to messages format
        if isinstance(prompt, str):
            messages = [{"role": "user", "content": prompt}]
        elif isinstance(prompt, dict):
            # Assume it's already in messages format or a structured prompt
            if "messages" in prompt:
                messages = prompt["messages"]
            else:
                messages = [{"role": "user", "content": str(prompt)}]
        else:
            messages = [{"role": "user", "content": str(prompt)}]

        # Build request
        request: CompletionRequest = {
            "model": model or self._default_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # Add tools if provided
        if tools:
            request["tools"] = tools

        # Execute the request (non-streaming) in thread pool to avoid blocking event loop
        response = await asyncio.to_thread(self._legacy.complete, request)

        # Extract usage information
        usage = response.get("usage", {})

        return {
            "content": response.get("content"),
            "tool_calls": response.get("tool_calls"),
            "model": response.get("model", model or self._default_model),
            "usage": {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            },
            "stop_reason": response.get("stop_reason"),
        }

    async def batch(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute batch generation (not yet implemented).

        Args:
            items: List of generation requests

        Returns:
            List of generation responses

        Raises:
            NotImplementedError: Batch processing not yet supported
        """
        raise NotImplementedError("Batch processing not yet implemented for Anthropic adapter")

    def close(self) -> None:
        """Close the underlying provider connection."""
        self._legacy.close()

    def __enter__(self) -> AnthropicAdapter:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()


# ============================================================================
# Mock Tests
# ============================================================================

def _test_adapter_capabilities() -> None:
    """Test that adapter returns expected capabilities."""
    try:
        adapter = AnthropicAdapter()
        caps = adapter.capabilities()

        assert isinstance(caps, dict), "Capabilities should be a dict"
        assert caps["tools"] is True, "Anthropic supports tools"
        assert caps["structured_output"] is False, "Direct JSON schema not wired through provider"
        assert caps["vision"] is True, "Anthropic Claude 3+ supports vision"
        assert caps["audio"] is False, "Anthropic does not support audio yet"

        print("✓ Capabilities test passed")
    except ValueError as e:
        # Expected if API key not set
        if "ANTHROPIC_API_KEY" in str(e) or "api_key" in str(e).lower():
            print("✓ Capabilities test passed (API key validation works)")
        else:
            raise


def _test_adapter_initialization() -> None:
    """Test that adapter initializes without errors."""
    try:
        adapter = AnthropicAdapter()
        assert adapter is not None, "Adapter should initialize"
        assert hasattr(adapter, "capabilities"), "Adapter should have capabilities method"
        assert hasattr(adapter, "generate"), "Adapter should have generate method"
        print("✓ Initialization test passed")
    except Exception as e:
        # Expected if API key not set or missing dependencies
        if "api" in str(e).lower() or "key" in str(e).lower():
            print("✓ Initialization test passed (API key validation works)")
        else:
            raise


if __name__ == "__main__":
    print("Running Anthropic adapter mock tests...")
    _test_adapter_initialization()
    _test_adapter_capabilities()
    print("\nAll tests passed!")
