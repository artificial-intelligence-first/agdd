"""Tests for Anthropic provider with tool_use and streaming support."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, Mock, patch


from magsag.providers.anthropic import (
    AnthropicProvider,
    CompletionRequest,
    OpenAIMessage,
    OpenAITool,
    convert_messages,
    convert_tools,
)


# ============================================================================
# Message Conversion Tests
# ============================================================================


def test_convert_messages_system_only() -> None:
    """Test conversion of system messages to system parameter."""
    messages: list[OpenAIMessage] = [
        {"role": "system", "content": "You are a helpful assistant."},
    ]

    system_prompt, anthropic_messages = convert_messages(messages)

    assert system_prompt == "You are a helpful assistant."
    assert len(anthropic_messages) == 0


def test_convert_messages_multiple_system() -> None:
    """Test that multiple system messages are combined."""
    messages: list[OpenAIMessage] = [
        {"role": "system", "content": "First instruction."},
        {"role": "system", "content": "Second instruction."},
    ]

    system_prompt, anthropic_messages = convert_messages(messages)

    assert system_prompt == "First instruction.\n\nSecond instruction."
    assert len(anthropic_messages) == 0


def test_convert_messages_user_assistant() -> None:
    """Test conversion of user and assistant messages."""
    messages: list[OpenAIMessage] = [
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    system_prompt, anthropic_messages = convert_messages(messages)

    assert system_prompt == "Be helpful."
    assert len(anthropic_messages) == 2
    assert anthropic_messages[0]["role"] == "user"
    assert anthropic_messages[0]["content"] == "Hello!"
    assert anthropic_messages[1]["role"] == "assistant"
    assert anthropic_messages[1]["content"] == "Hi there!"


def test_convert_messages_assistant_with_tool_calls() -> None:
    """Test conversion of assistant messages with tool_calls to tool_use blocks."""
    messages: list[OpenAIMessage] = [
        {"role": "user", "content": "What's the weather?"},
        {
            "role": "assistant",
            "content": "Let me check the weather for you.",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"location": "NYC"}'},
                }
            ],
        },
    ]

    system_prompt, anthropic_messages = convert_messages(messages)

    assert system_prompt is None
    assert len(anthropic_messages) == 2

    # Assistant message should have content blocks
    assistant_msg = anthropic_messages[1]
    assert assistant_msg["role"] == "assistant"
    assert isinstance(assistant_msg["content"], list)
    assert len(assistant_msg["content"]) == 2

    # First block should be text
    text_block = assistant_msg["content"][0]
    assert text_block["type"] == "text"
    assert text_block["text"] == "Let me check the weather for you."

    # Second block should be tool_use
    tool_use_block = assistant_msg["content"][1]
    assert tool_use_block["type"] == "tool_use"
    assert tool_use_block["id"] == "call_123"
    assert tool_use_block["name"] == "get_weather"
    assert tool_use_block["input"] == {"location": "NYC"}


def test_convert_messages_tool_response() -> None:
    """Test conversion of tool response messages."""
    assistant_call = cast(
        OpenAIMessage,
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"location": "NYC"}'},
                }
            ],
        },
    )
    messages: list[OpenAIMessage] = [
        {"role": "user", "content": "What's the weather?"},
        assistant_call,
        {
            "role": "tool",
            "tool_call_id": "call_123",
            "content": '{"temperature": 72, "condition": "sunny"}',
        },
    ]

    system_prompt, anthropic_messages = convert_messages(messages)

    assert system_prompt is None
    assert len(anthropic_messages) == 3

    # Assistant message with tool_use
    assistant_msg = anthropic_messages[1]
    assert assistant_msg["role"] == "assistant"
    assert isinstance(assistant_msg["content"], list)
    tool_use_block = assistant_msg["content"][0]
    assert tool_use_block["type"] == "tool_use"
    assert tool_use_block["id"] == "call_123"
    assert tool_use_block["name"] == "get_weather"

    # Tool result should be in user message
    tool_result_msg = anthropic_messages[2]
    assert tool_result_msg["role"] == "user"
    assert isinstance(tool_result_msg["content"], list)
    tool_result = tool_result_msg["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "call_123"


def test_convert_messages_no_system() -> None:
    """Test conversion when no system messages present."""
    messages: list[OpenAIMessage] = [
        {"role": "user", "content": "Hello!"},
    ]

    system_prompt, anthropic_messages = convert_messages(messages)

    assert system_prompt is None
    assert len(anthropic_messages) == 1


# ============================================================================
# Tool Conversion Tests
# ============================================================================


def test_convert_tools_single() -> None:
    """Test conversion of single tool definition."""
    tools: list[OpenAITool] = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string", "description": "City name"}},
                    "required": ["location"],
                },
            },
        }
    ]

    anthropic_tools = convert_tools(tools)

    assert anthropic_tools is not None
    assert len(anthropic_tools) == 1
    assert anthropic_tools[0]["name"] == "get_weather"
    assert anthropic_tools[0]["description"] == "Get current weather"
    assert "location" in anthropic_tools[0]["input_schema"]["properties"]


def test_convert_tools_multiple() -> None:
    """Test conversion of multiple tool definitions."""
    tools: list[OpenAITool] = [
        {
            "type": "function",
            "function": {
                "name": "tool1",
                "description": "First tool",
                "parameters": {"type": "object"},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "tool2",
                "description": "Second tool",
                "parameters": {"type": "object"},
            },
        },
    ]

    anthropic_tools = convert_tools(tools)

    assert anthropic_tools is not None
    assert len(anthropic_tools) == 2
    assert anthropic_tools[0]["name"] == "tool1"
    assert anthropic_tools[1]["name"] == "tool2"


def test_convert_tools_none() -> None:
    """Test conversion when no tools provided."""
    assert convert_tools(None) is None
    assert convert_tools([]) is None


# ============================================================================
# Provider Tests - Non-Streaming
# ============================================================================


@patch("magsag.providers.anthropic.httpx.Client")
def test_provider_complete_basic(mock_client_class: Mock) -> None:
    """Test basic completion request without tools."""
    # Setup mock
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": "msg_123",
        "model": "claude-3-5-sonnet-20241022",
        "content": [{"type": "text", "text": "Hello!"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    mock_response.raise_for_status = Mock()

    mock_client = Mock()
    mock_client.post.return_value = mock_response
    mock_client_class.return_value = mock_client

    # Execute
    provider = AnthropicProvider(api_key="test-key")
    request: CompletionRequest = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 1024,
    }

    response = provider.complete(request)

    # Verify
    assert response["id"] == "msg_123"
    assert response["content"] == "Hello!"
    assert response["role"] == "assistant"
    assert response["stop_reason"] == "end_turn"
    assert response["tool_calls"] is None


@patch("magsag.providers.anthropic.httpx.Client")
def test_provider_complete_with_tool_use(mock_client_class: Mock) -> None:
    """Test completion with tool_use stop_reason."""
    # Setup mock with tool_use response
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": "msg_456",
        "model": "claude-3-5-sonnet-20241022",
        "content": [
            {"type": "text", "text": "Let me check the weather."},
            {
                "type": "tool_use",
                "id": "toolu_123",
                "name": "get_weather",
                "input": {"location": "San Francisco"},
            },
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 50, "output_tokens": 30},
    }
    mock_response.raise_for_status = Mock()

    mock_client = Mock()
    mock_client.post.return_value = mock_response
    mock_client_class.return_value = mock_client

    # Execute
    provider = AnthropicProvider(api_key="test-key")
    request: CompletionRequest = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "What's the weather in SF?"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object"},
                },
            }
        ],
        "max_tokens": 1024,
    }

    response = provider.complete(request)

    # Verify normalized tool_calls
    assert response["id"] == "msg_456"
    assert response["content"] == "Let me check the weather."
    assert response["stop_reason"] == "tool_use"
    assert response["tool_calls"] is not None
    assert len(response["tool_calls"]) == 1

    tool_call = response["tool_calls"][0]
    assert tool_call["id"] == "toolu_123"
    assert tool_call["type"] == "function"
    assert tool_call["function"]["name"] == "get_weather"
    assert tool_call["function"]["arguments"] == {"location": "San Francisco"}


@patch("magsag.providers.anthropic.httpx.Client")
def test_provider_complete_with_system(mock_client_class: Mock) -> None:
    """Test that system messages are properly converted to system parameter."""
    # Setup mock
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": "msg_789",
        "model": "claude-3-5-sonnet-20241022",
        "content": [{"type": "text", "text": "Response"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 20, "output_tokens": 10},
    }
    mock_response.raise_for_status = Mock()

    mock_client = Mock()
    mock_client.post.return_value = mock_response
    mock_client_class.return_value = mock_client

    # Execute
    provider = AnthropicProvider(api_key="test-key")
    request: CompletionRequest = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ],
        "max_tokens": 1024,
    }

    provider.complete(request)

    # Verify that system was sent in payload
    call_args = mock_client.post.call_args
    payload = call_args[1]["json"]
    assert payload["system"] == "You are helpful."
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["role"] == "user"


# ============================================================================
# Provider Tests - Streaming
# ============================================================================


@patch("magsag.providers.anthropic.httpx.Client")
def test_provider_stream_text(mock_client_class: Mock) -> None:
    """Test streaming with incremental text deltas."""
    # Mock SSE stream
    sse_lines = [
        'data: {"type": "message_start", "message": {"id": "msg_001"}}',
        'data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}}',
        'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}',
        'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": " world"}}',
        'data: {"type": "content_block_stop", "index": 0}',
        'data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}',
        "data: [DONE]",
    ]

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = iter(sse_lines)
    mock_response.raise_for_status = Mock()
    mock_response.__enter__ = Mock(return_value=mock_response)
    mock_response.__exit__ = Mock()

    mock_client = Mock()
    mock_client.stream.return_value = mock_response
    mock_client_class.return_value = mock_client

    # Execute
    provider = AnthropicProvider(api_key="test-key")
    request: CompletionRequest = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 1024,
        "stream": True,
    }

    deltas = list(provider.stream(request))

    # Verify incremental text
    assert len(deltas) == 2
    assert deltas[0]["type"] == "text"
    assert deltas[0]["text"] == "Hello"
    assert deltas[1]["type"] == "text"
    assert deltas[1]["text"] == " world"


@patch("magsag.providers.anthropic.httpx.Client")
def test_provider_stream_tool_use(mock_client_class: Mock) -> None:
    """Test streaming with tool_use events."""
    # Mock SSE stream with tool use
    sse_lines = [
        'data: {"type": "message_start", "message": {"id": "msg_002"}}',
        'data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}}',
        'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Checking..."}}',
        'data: {"type": "content_block_stop", "index": 0}',
        'data: {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_999", "name": "get_weather"}}',
        'data: {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{\\"location\\":"}}',
        'data: {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": " \\"NYC\\"}"}}',
        'data: {"type": "content_block_stop", "index": 1}',
        'data: {"type": "message_delta", "delta": {"stop_reason": "tool_use"}}',
        "data: [DONE]",
    ]

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = iter(sse_lines)
    mock_response.raise_for_status = Mock()
    mock_response.__enter__ = Mock(return_value=mock_response)
    mock_response.__exit__ = Mock()

    mock_client = Mock()
    mock_client.stream.return_value = mock_response
    mock_client_class.return_value = mock_client

    # Execute
    provider = AnthropicProvider(api_key="test-key")
    request: CompletionRequest = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "Weather?"}],
        "tools": [
            {
                "type": "function",
                "function": {"name": "get_weather", "description": "Get weather", "parameters": {}},
            }
        ],
        "max_tokens": 1024,
        "stream": True,
    }

    deltas = list(provider.stream(request, use_tool_streaming=True))

    # Verify events
    assert len(deltas) >= 3

    # Text delta
    assert deltas[0]["type"] == "text"
    assert deltas[0]["text"] == "Checking..."

    # Tool use start
    assert deltas[1]["type"] == "tool_use"
    tool_use_start = deltas[1]["tool_use"]
    assert tool_use_start is not None
    assert tool_use_start["id"] == "toolu_999"
    assert tool_use_start["name"] == "get_weather"

    # Tool input deltas (fine-grained streaming)
    assert deltas[2]["type"] == "tool_call_delta"
    tool_delta_text = deltas[2]["text"]
    assert tool_delta_text is not None
    assert '"location":' in tool_delta_text


@patch("magsag.providers.anthropic.httpx.Client")
def test_provider_stream_tool_use_without_fine_grained(mock_client_class: Mock) -> None:
    """Test streaming with tool_use when fine-grained streaming is disabled.

    When fine-grained streaming is off, the full tool input is sent in content_block_start.
    """
    # Mock SSE stream with full tool input in content_block_start
    sse_lines = [
        'data: {"type": "message_start", "message": {"id": "msg_003"}}',
        'data: {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "toolu_abc", "name": "get_weather", "input": {"location": "Tokyo", "unit": "celsius"}}}',
        'data: {"type": "content_block_stop", "index": 0}',
        'data: {"type": "message_delta", "delta": {"stop_reason": "tool_use"}}',
        "data: [DONE]",
    ]

    mock_response = MagicMock()
    mock_response.iter_lines.return_value = iter(sse_lines)
    mock_response.raise_for_status = Mock()
    mock_response.__enter__ = Mock(return_value=mock_response)
    mock_response.__exit__ = Mock()

    mock_client = Mock()
    mock_client.stream.return_value = mock_response
    mock_client_class.return_value = mock_client

    # Execute with fine-grained streaming disabled (default)
    provider = AnthropicProvider(api_key="test-key")
    request: CompletionRequest = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "What's the weather in Tokyo?"}],
        "tools": [
            {
                "type": "function",
                "function": {"name": "get_weather", "description": "Get weather", "parameters": {}},
            }
        ],
        "max_tokens": 1024,
        "stream": True,
    }

    deltas = list(provider.stream(request, use_tool_streaming=False))

    # Verify tool_use event includes full input
    assert len(deltas) == 1
    assert deltas[0]["type"] == "tool_use"
    tool_use_event = deltas[0]["tool_use"]
    assert tool_use_event is not None
    assert tool_use_event["id"] == "toolu_abc"
    assert tool_use_event["name"] == "get_weather"
    # This is the critical assertion - input must be included
    assert tool_use_event["input"] == {"location": "Tokyo", "unit": "celsius"}


@patch("magsag.providers.anthropic.httpx.Client")
def test_provider_headers_with_tool_streaming(mock_client_class: Mock) -> None:
    """Test that fine-grained tool streaming beta header is included when requested."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": "msg_123",
        "model": "claude-3-5-sonnet-20241022",
        "content": [{"type": "text", "text": "Test"}],
        "stop_reason": "end_turn",
    }
    mock_response.raise_for_status = Mock()

    mock_client = Mock()
    mock_client.post.return_value = mock_response
    mock_client_class.return_value = mock_client

    # Execute with tool streaming enabled
    provider = AnthropicProvider(api_key="test-key")
    request: CompletionRequest = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": [{"role": "user", "content": "Test"}],
        "max_tokens": 1024,
    }

    provider.complete(request, use_tool_streaming=True)

    # Verify beta header included
    call_args = mock_client.post.call_args
    headers = call_args[1]["headers"]
    assert "anthropic-beta" in headers
    assert headers["anthropic-beta"] == "fine-grained-tool-streaming-2024-11-19"


# ============================================================================
# Integration Tests
# ============================================================================


def test_provider_context_manager() -> None:
    """Test provider can be used as context manager."""
    with AnthropicProvider(api_key="test") as provider:
        assert provider is not None

    # Client should be closed after context exit
    # (verify by checking no exceptions raised)


def test_provider_default_model() -> None:
    """Test default model configuration."""
    provider = AnthropicProvider(api_key="test", default_model="claude-3-opus-20240229")
    assert provider.default_model == "claude-3-opus-20240229"


def test_provider_api_key_from_env() -> None:
    """Test API key loaded from environment variable."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-key"}):
        provider = AnthropicProvider()
        assert provider.api_key == "env-key"


def test_provider_custom_base_url() -> None:
    """Test custom base URL configuration."""
    provider = AnthropicProvider(api_key="test", base_url="https://custom.api.com/v1/")
    assert provider.base_url == "https://custom.api.com/v1"
