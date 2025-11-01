"""Provider SPI for LLM backend abstraction.

This module defines the Provider protocol that all LLM provider implementations
must satisfy, enabling pluggable backends with consistent interfaces for
text, vision, and audio generation with optional tool calling and structured output.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from magsag.core.types import CapabilityMatrix


class Provider(Protocol):
    """Protocol for LLM provider implementations.

    Providers must implement capability introspection, single generation,
    and batch processing methods with consistent interfaces across all backends.
    """

    def capabilities(self) -> CapabilityMatrix:
        """Report the capability matrix supported by this provider.

        Returns:
            CapabilityMatrix describing which features (tools, structured output,
            vision, audio) are supported by this provider implementation.
        """
        ...

    async def generate(
        self,
        prompt: dict[str, Any],
        tools: list[dict[str, Any]] | None = None,
        *,
        mode: Literal["text", "vision", "audio"] = "text",
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a single completion from the provider.

        Args:
            prompt: Structured prompt dictionary with messages and parameters.
            tools: Optional list of tool/function definitions for tool calling.
            mode: Generation mode - "text" for text-only, "vision" for image input,
                "audio" for audio input processing.
            schema: Optional JSON schema for structured output constraint.

        Returns:
            Dictionary containing generation result with keys:
                - content: Generated text content
                - tool_calls: List of tool calls if applicable
                - usage: Token usage statistics
                - finish_reason: Completion reason (stop, length, tool_calls, etc.)

        Raises:
            ValueError: If requested mode is not supported by provider capabilities.
            RuntimeError: If provider API call fails.
        """
        ...

    async def batch(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Process multiple generation requests in batch mode for cost optimization.

        Args:
            items: List of generation request dictionaries, each containing
                same fields as single generate() call (prompt, tools, mode, schema).

        Returns:
            List of generation results in same order as input items, with same
            structure as single generate() response.

        Raises:
            RuntimeError: If batch API is not available or fails.

        Note:
            Batch processing may have higher latency but lower cost per request.
            Providers without native batch support may fall back to sequential
            processing with this interface.
        """
        ...
