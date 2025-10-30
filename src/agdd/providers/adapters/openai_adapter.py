"""OpenAI Provider SPI Adapter.

This adapter wraps the existing OpenAI provider implementation to conform
to the Provider SPI protocol.
"""

from __future__ import annotations

import asyncio
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

from agdd.providers.openai import OpenAIProvider, CompletionRequest, ProviderConfig


class OpenAIAdapter:
    """SPI-compliant adapter for OpenAI provider.

    This adapter wraps the existing OpenAIProvider to provide a standardized
    interface that conforms to the Provider SPI protocol.
    """

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        """Initialize the adapter with an OpenAI provider.

        Args:
            config: Optional provider configuration. If not provided,
                   a default configuration will be used.
        """
        self._legacy = OpenAIProvider(config=config)
        self._config = config or ProviderConfig()

    def capabilities(self) -> dict[str, bool]:
        """Return capability matrix for OpenAI models.

        Returns:
            Dictionary describing model capabilities:
            - tools: Function/tool calling support
            - structured_output: JSON mode and structured outputs
            - vision: Image understanding (GPT-4V models)
            - audio: Audio processing capabilities
        """
        return {
            "tools": True,
            "structured_output": True,
            "vision": True,  # Available in gpt-4-vision and gpt-4o
            "audio": False,  # Not yet supported via standard API
        }

    async def generate(
        self,
        prompt: dict[str, Any] | str,
        tools: Optional[list[dict[str, Any]]] = None,
        *,
        mode: Literal["text", "vision", "audio"] = "text",
        schema: Optional[dict[str, Any]] = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a completion using the OpenAI provider.

        Args:
            prompt: Input prompt, either as string or structured dict with messages
            tools: Optional list of tool/function definitions
            mode: Generation mode (text, vision, or audio)
            schema: Optional JSON schema for structured output
            model: Model identifier to use
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            Dictionary containing:
            - content: Generated text content
            - tool_calls: List of tool calls if any
            - model: Model used
            - usage: Token usage information
            - finish_reason: Completion finish reason
        """
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
        request = CompletionRequest(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Add tools if provided
        if tools:
            from openai import NOT_GIVEN
            request.tools = tools

        # Add response format if schema provided
        if schema:
            request.response_format = {"type": "json_schema", "json_schema": schema}

        # Execute the request (non-streaming) in thread pool to avoid blocking event loop
        response = await asyncio.to_thread(self._legacy.complete, request)

        # Convert to SPI format
        return {
            "content": response.content,
            "tool_calls": response.tool_calls,
            "model": response.model,
            "usage": {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "cost_usd": response.usage.total_cost_usd,
            },
            "finish_reason": response.finish_reason,
            "endpoint_used": response.endpoint_used.value,
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
        raise NotImplementedError("Batch processing not yet implemented for OpenAI adapter")


# ============================================================================
# Mock Tests
# ============================================================================

def _test_adapter_capabilities() -> None:
    """Test that adapter returns expected capabilities."""
    adapter = OpenAIAdapter()
    caps = adapter.capabilities()

    assert isinstance(caps, dict), "Capabilities should be a dict"
    assert caps["tools"] is True, "OpenAI supports tools"
    assert caps["structured_output"] is True, "OpenAI supports structured output"
    assert caps["vision"] is True, "OpenAI supports vision"
    assert caps["audio"] is False, "OpenAI does not support audio via standard API"

    print("✓ Capabilities test passed")


def _test_adapter_initialization() -> None:
    """Test that adapter initializes without errors."""
    try:
        adapter = OpenAIAdapter()
        assert adapter is not None, "Adapter should initialize"
        assert hasattr(adapter, "capabilities"), "Adapter should have capabilities method"
        assert hasattr(adapter, "generate"), "Adapter should have generate method"
        print("✓ Initialization test passed")
    except ValueError as e:
        # Expected if API key not set
        if "OPENAI_API_KEY" in str(e):
            print("✓ Initialization test passed (API key validation works)")
        else:
            raise


if __name__ == "__main__":
    print("Running OpenAI adapter mock tests...")
    _test_adapter_initialization()
    _test_adapter_capabilities()
    print("\nAll tests passed!")
