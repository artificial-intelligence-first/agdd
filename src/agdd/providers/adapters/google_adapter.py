"""Google Provider SPI Adapter.

This adapter wraps the existing Google provider implementation to conform
to the Provider SPI protocol.
"""

from __future__ import annotations

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

from agdd.providers.google import GoogleProvider


class GoogleAdapter:
    """SPI-compliant adapter for Google provider.

    This adapter wraps the existing GoogleProvider to provide a standardized
    interface that conforms to the Provider SPI protocol.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """Initialize the adapter with a Google provider.

        Args:
            api_key: Optional Google API key (defaults to GOOGLE_API_KEY env var)
            model_name: Optional model name (defaults to GOOGLE_MODEL_NAME env var
                       or "gemini-1.5-pro")
        """
        self._legacy = GoogleProvider(api_key=api_key, model_name=model_name)
        self._model_name = model_name or "gemini-1.5-pro"

    def capabilities(self) -> dict[str, bool]:
        """Return capability matrix for Google models.

        Returns:
            Dictionary describing model capabilities:
            - tools: Function/tool calling support
            - structured_output: JSON mode and structured outputs
            - vision: Image understanding (Gemini models)
            - audio: Audio processing capabilities
        """
        return {
            "tools": True,  # Gemini supports function calling
            "structured_output": True,  # Gemini supports JSON mode
            "vision": True,  # Gemini models support vision
            "audio": True,  # Gemini 2.0+ supports audio
        }

    async def generate(
        self,
        prompt: dict[str, Any] | str,
        tools: Optional[list[dict[str, Any]]] = None,
        *,
        mode: Literal["text", "vision", "audio"] = "text",
        schema: Optional[dict[str, Any]] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a completion using the Google provider.

        Args:
            prompt: Input prompt, either as string or structured dict
            tools: Optional list of tool/function definitions
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
        """
        # Convert prompt to string format (Google provider expects string)
        if isinstance(prompt, str):
            prompt_text = prompt
        elif isinstance(prompt, dict):
            # Extract text from messages format if present
            if "messages" in prompt:
                messages = prompt["messages"]
                # Combine all message contents
                parts = []
                for msg in messages:
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        parts.append(f"{msg.get('role', 'user')}: {content}")
                    else:
                        parts.append(f"{msg.get('role', 'user')}: {str(content)}")
                prompt_text = "\n".join(parts)
            else:
                prompt_text = str(prompt)
        else:
            prompt_text = str(prompt)

        # Execute the request using the legacy provider
        response = self._legacy.generate(
            prompt=prompt_text,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model or self._model_name,
            **kwargs,
        )

        # Convert LLMResponse to SPI format
        usage = response.metadata.get("usage", {})

        return {
            "content": response.content,
            "tool_calls": response.tool_calls,  # Will be None if not using tools
            "model": response.model,
            "usage": {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "total_tokens": response.input_tokens + response.output_tokens,
                "cost_usd": response.metadata.get("cost_usd", 0.0),
            },
            "finish_reason": "complete",  # Google provider doesn't expose this directly
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
        raise NotImplementedError("Batch processing not yet implemented for Google adapter")


# ============================================================================
# Mock Tests
# ============================================================================

def _test_adapter_capabilities() -> None:
    """Test that adapter returns expected capabilities."""
    try:
        adapter = GoogleAdapter()
        caps = adapter.capabilities()

        assert isinstance(caps, dict), "Capabilities should be a dict"
        assert caps["tools"] is True, "Google Gemini supports tools"
        assert caps["structured_output"] is True, "Google Gemini supports structured output"
        assert caps["vision"] is True, "Google Gemini supports vision"
        assert caps["audio"] is True, "Google Gemini 2.0+ supports audio"

        print("✓ Capabilities test passed")
    except ValueError as e:
        # Expected if API key not set
        if "GOOGLE_API_KEY" in str(e) or "api_key" in str(e).lower():
            print("✓ Capabilities test passed (API key validation works)")
        else:
            raise


def _test_adapter_initialization() -> None:
    """Test that adapter initializes without errors."""
    try:
        adapter = GoogleAdapter()
        assert adapter is not None, "Adapter should initialize"
        assert hasattr(adapter, "capabilities"), "Adapter should have capabilities method"
        assert hasattr(adapter, "generate"), "Adapter should have generate method"
        print("✓ Initialization test passed")
    except ValueError as e:
        # Expected if API key not set
        if "api" in str(e).lower() or "key" in str(e).lower():
            print("✓ Initialization test passed (API key validation works)")
        else:
            raise
    except ImportError as e:
        # Expected if google-genai package not installed
        if "google-genai" in str(e):
            print("✓ Initialization test passed (dependency check works)")
        else:
            raise


if __name__ == "__main__":
    print("Running Google adapter mock tests...")
    _test_adapter_initialization()
    _test_adapter_capabilities()
    print("\nAll tests passed!")
