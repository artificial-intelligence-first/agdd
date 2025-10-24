"""Anthropic Messages API provider with tool and streaming support.

This module translates OpenAI-compatible requests to Anthropic Messages API format,
with special handling for:
- System messages (OpenAI role -> Anthropic system parameter)
- Tool definitions and tool_use events
- Streaming responses with incremental text and tool events
"""

from __future__ import annotations

import os
from typing import Any, AsyncIterator, Iterator, Literal, TypedDict, cast

import httpx

# ============================================================================
# Type Definitions
# ============================================================================


class OpenAIMessage(TypedDict, total=False):
    """OpenAI-style message format."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]]
    name: str | None
    tool_calls: list[dict[str, Any]] | None
    tool_call_id: str | None


class OpenAITool(TypedDict):
    """OpenAI-style tool definition."""

    type: Literal["function"]
    function: dict[str, Any]


class AnthropicMessage(TypedDict, total=False):
    """Anthropic Messages API message format."""

    role: Literal["user", "assistant"]
    content: str | list[dict[str, Any]]


class AnthropicTool(TypedDict):
    """Anthropic tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any]


class CompletionRequest(TypedDict, total=False):
    """OpenAI-compatible completion request."""

    model: str
    messages: list[OpenAIMessage]
    tools: list[OpenAITool] | None
    max_tokens: int
    temperature: float | None
    top_p: float | None
    stream: bool


class ToolCall(TypedDict):
    """Normalized tool call representation."""

    id: str
    type: Literal["function"]
    function: dict[str, Any]


class CompletionResponse(TypedDict, total=False):
    """Normalized completion response."""

    id: str
    model: str
    role: Literal["assistant"]
    content: str | None
    tool_calls: list[ToolCall] | None
    stop_reason: str | None
    usage: dict[str, int] | None


class StreamDelta(TypedDict, total=False):
    """Normalized streaming delta."""

    type: Literal["text", "tool_use", "tool_call_delta"]
    text: str | None
    tool_use: dict[str, Any] | None
    index: int | None


# ============================================================================
# Message Conversion
# ============================================================================


def convert_messages(
    messages: list[OpenAIMessage],
) -> tuple[str | None, list[AnthropicMessage]]:
    """Convert OpenAI messages to Anthropic format.

    Extracts system messages as a single system parameter and converts
    remaining messages to Anthropic format.

    Args:
        messages: OpenAI-style messages

    Returns:
        Tuple of (system_prompt, anthropic_messages)

    Raises:
        ValueError: If message format is invalid
    """
    system_parts: list[str] = []
    anthropic_messages: list[AnthropicMessage] = []

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")

        if role == "system":
            # Collect all system messages into single system parameter
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list):
                # Extract text from content blocks
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        system_parts.append(cast(str, block.get("text", "")))
        elif role == "user" or role == "assistant":
            # Convert to Anthropic message format
            anthropic_msg: AnthropicMessage = {
                "role": role,
                "content": content if isinstance(content, str) else content,
            }
            anthropic_messages.append(anthropic_msg)
        elif role == "tool":
            # Convert tool response to user message with tool_result content
            tool_call_id = msg.get("tool_call_id", "")
            tool_content: list[dict[str, Any]] = [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": content if isinstance(content, str) else str(content),
                }
            ]
            anthropic_msg = {"role": "user", "content": tool_content}
            anthropic_messages.append(anthropic_msg)

    system_prompt = "\n\n".join(system_parts) if system_parts else None
    return system_prompt, anthropic_messages


def convert_tools(tools: list[OpenAITool] | None) -> list[AnthropicTool] | None:
    """Convert OpenAI tool definitions to Anthropic format.

    Args:
        tools: OpenAI-style tool definitions

    Returns:
        Anthropic-style tool definitions or None
    """
    if not tools:
        return None

    anthropic_tools: list[AnthropicTool] = []
    for tool in tools:
        if tool.get("type") != "function":
            continue

        func = tool.get("function", {})
        anthropic_tool: AnthropicTool = {
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {}),
        }
        anthropic_tools.append(anthropic_tool)

    return anthropic_tools if anthropic_tools else None


# ============================================================================
# API Client
# ============================================================================


class AnthropicProvider:
    """Anthropic Messages API provider with tool and streaming support."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com/v1",
        default_model: str = "claude-3-5-sonnet-20241022",
    ):
        """Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            base_url: API base URL
            default_model: Default model to use
        """
        self.api_key: str = (
            api_key if api_key is not None else (os.getenv("ANTHROPIC_API_KEY") or "")
        )
        self.base_url: str = base_url.rstrip("/")
        self.default_model: str = default_model
        self.client: httpx.Client = httpx.Client(timeout=120.0)

    def _build_headers(self, use_tool_streaming: bool = False) -> dict[str, str]:
        """Build request headers.

        Args:
            use_tool_streaming: Whether to include fine-grained tool streaming beta header

        Returns:
            Request headers
        """
        headers: dict[str, str] = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Optional: Enable fine-grained tool streaming beta
        if use_tool_streaming:
            headers["anthropic-beta"] = "fine-grained-tool-streaming-2024-11-19"

        return headers

    def complete(
        self,
        request: CompletionRequest,
        use_tool_streaming: bool = False,
    ) -> CompletionResponse:
        """Execute non-streaming completion request.

        Args:
            request: Completion request
            use_tool_streaming: Whether to enable fine-grained tool streaming

        Returns:
            Normalized completion response

        Raises:
            httpx.HTTPError: On API errors
        """
        system_prompt, messages = convert_messages(request["messages"])
        tools = convert_tools(request.get("tools"))

        # Build Anthropic request payload
        payload: dict[str, Any] = {
            "model": request.get("model", self.default_model),
            "messages": messages,
            "max_tokens": request.get("max_tokens", 4096),
        }

        if system_prompt:
            payload["system"] = system_prompt

        if tools:
            payload["tools"] = tools

        if request.get("temperature") is not None:
            payload["temperature"] = request["temperature"]

        if request.get("top_p") is not None:
            payload["top_p"] = request["top_p"]

        # Execute request
        response = self.client.post(
            f"{self.base_url}/messages",
            headers=self._build_headers(use_tool_streaming),
            json=payload,
        )
        response.raise_for_status()

        data = response.json()

        # Normalize response
        return self._normalize_response(data)

    def stream(
        self,
        request: CompletionRequest,
        use_tool_streaming: bool = False,
    ) -> Iterator[StreamDelta]:
        """Execute streaming completion request.

        Args:
            request: Completion request
            use_tool_streaming: Whether to enable fine-grained tool streaming

        Yields:
            Streaming deltas with incremental text and tool events

        Raises:
            httpx.HTTPError: On API errors
        """
        system_prompt, messages = convert_messages(request["messages"])
        tools = convert_tools(request.get("tools"))

        # Build Anthropic request payload
        payload: dict[str, Any] = {
            "model": request.get("model", self.default_model),
            "messages": messages,
            "max_tokens": request.get("max_tokens", 4096),
            "stream": True,
        }

        if system_prompt:
            payload["system"] = system_prompt

        if tools:
            payload["tools"] = tools

        if request.get("temperature") is not None:
            payload["temperature"] = request["temperature"]

        if request.get("top_p") is not None:
            payload["top_p"] = request["top_p"]

        # Execute streaming request
        with self.client.stream(
            "POST",
            f"{self.base_url}/messages",
            headers=self._build_headers(use_tool_streaming),
            json=payload,
        ) as response:
            response.raise_for_status()

            # Process SSE stream
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:]  # Remove "data: " prefix
                if data_str == "[DONE]":
                    break

                import json

                try:
                    event = json.loads(data_str)
                    delta = self._process_stream_event(event)
                    if delta:
                        yield delta
                except json.JSONDecodeError:
                    continue

    async def stream_async(
        self,
        request: CompletionRequest,
        use_tool_streaming: bool = False,
    ) -> AsyncIterator[StreamDelta]:
        """Execute async streaming completion request.

        Args:
            request: Completion request
            use_tool_streaming: Whether to enable fine-grained tool streaming

        Yields:
            Streaming deltas with incremental text and tool events

        Raises:
            httpx.HTTPError: On API errors
        """
        system_prompt, messages = convert_messages(request["messages"])
        tools = convert_tools(request.get("tools"))

        # Build Anthropic request payload
        payload: dict[str, Any] = {
            "model": request.get("model", self.default_model),
            "messages": messages,
            "max_tokens": request.get("max_tokens", 4096),
            "stream": True,
        }

        if system_prompt:
            payload["system"] = system_prompt

        if tools:
            payload["tools"] = tools

        if request.get("temperature") is not None:
            payload["temperature"] = request["temperature"]

        if request.get("top_p") is not None:
            payload["top_p"] = request["top_p"]

        # Execute async streaming request
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/messages",
                headers=self._build_headers(use_tool_streaming),
                json=payload,
            ) as response:
                response.raise_for_status()

                # Process SSE stream
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]  # Remove "data: " prefix
                    if data_str == "[DONE]":
                        break

                    import json

                    try:
                        event = json.loads(data_str)
                        delta = self._process_stream_event(event)
                        if delta:
                            yield delta
                    except json.JSONDecodeError:
                        continue

    def _normalize_response(self, data: dict[str, Any]) -> CompletionResponse:
        """Normalize Anthropic response to common format.

        Args:
            data: Raw Anthropic API response

        Returns:
            Normalized response with tool_calls extracted
        """
        response: CompletionResponse = {
            "id": data.get("id", ""),
            "model": data.get("model", ""),
            "role": "assistant",
            "stop_reason": data.get("stop_reason"),
            "usage": data.get("usage"),
        }

        # Extract content and tool_calls
        content_blocks = data.get("content", [])
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_call: ToolCall = {
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": block.get("input", {}),
                    },
                }
                tool_calls.append(tool_call)

        response["content"] = "\n".join(text_parts) if text_parts else None
        response["tool_calls"] = tool_calls if tool_calls else None

        return response

    def _process_stream_event(self, event: dict[str, Any]) -> StreamDelta | None:
        """Process streaming event and extract delta.

        Args:
            event: Streaming event from Anthropic API

        Returns:
            Normalized delta or None if not a content event
        """
        event_type = event.get("type")

        if event_type == "content_block_delta":
            delta_data = event.get("delta", {})
            delta_type = delta_data.get("type")

            if delta_type == "text_delta":
                # Incremental text
                return StreamDelta(
                    type="text",
                    text=delta_data.get("text"),
                    index=event.get("index"),
                )
            elif delta_type == "input_json_delta":
                # Tool input streaming (fine-grained beta)
                return StreamDelta(
                    type="tool_call_delta",
                    text=delta_data.get("partial_json"),
                    index=event.get("index"),
                )

        elif event_type == "content_block_start":
            # Tool use block started
            content_block = event.get("content_block", {})
            if content_block.get("type") == "tool_use":
                return StreamDelta(
                    type="tool_use",
                    tool_use={
                        "id": content_block.get("id"),
                        "name": content_block.get("name"),
                    },
                    index=event.get("index"),
                )

        return None

    def close(self) -> None:
        """Close HTTP client."""
        self.client.close()

    def __enter__(self) -> AnthropicProvider:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
