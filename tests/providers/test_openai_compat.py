"""Tests for OpenAICompatProvider with fallback behavior."""

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from magsag.providers.base import LLMResponse
from magsag.providers.openai_compat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    OpenAICompatProvider,
    OpenAICompatProviderConfig,
    ProviderCapabilities,
)


@pytest.fixture
def provider_config() -> OpenAICompatProviderConfig:
    """Create test provider configuration."""
    return OpenAICompatProviderConfig(
        base_url="http://localhost:8000/v1/",
        timeout=30.0,
        api_key="test-key",
    )


@pytest.fixture
def mock_response() -> dict[str, Any]:
    """Create mock chat completion response."""
    return {
        "id": "chatcmpl-123",
        "model": "llama-2-7b",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


@pytest.mark.asyncio
async def test_provider_capabilities(
    provider_config: OpenAICompatProviderConfig,
) -> None:
    """Test that OpenAICompatProvider reports correct capabilities."""
    provider = OpenAICompatProvider(config=provider_config)
    capabilities = provider.get_capabilities()

    assert isinstance(capabilities, ProviderCapabilities)
    assert capabilities.supports_chat is True
    assert capabilities.supports_responses is False
    assert capabilities.supports_streaming is False  # P1 fix: disabled
    assert capabilities.supports_function_calling is False

    await provider.close()


@pytest.mark.asyncio
async def test_basic_chat_completion_no_fallback(
    provider_config: OpenAICompatProviderConfig, mock_response: dict[str, Any]
) -> None:
    """Test basic chat completion without fallback (no response_format or stream)."""
    provider = OpenAICompatProvider(config=provider_config)

    request = ChatCompletionRequest(
        model="llama-2-7b",
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.7,
        max_tokens=100,
    )

    # Mock the HTTP client
    with patch.object(provider._client, "post", new_callable=AsyncMock) as mock_post:
        mock_http_response = Mock(spec=httpx.Response)
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = Mock()
        mock_post.return_value = mock_http_response

        response = await provider.chat_completion(request)

        # Verify request was made correctly with relative path (P1 fix)
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "chat/completions"  # P1 fix: relative path

        # Verify payload does not contain response_format or stream
        payload = call_args[1]["json"]
        assert "response_format" not in payload
        assert "stream" not in payload
        assert payload["model"] == "llama-2-7b"
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 100

        # Verify response
        assert response.id == "chatcmpl-123"
        assert response.model == "llama-2-7b"
        assert len(response.choices) == 1

    await provider.close()


@pytest.mark.asyncio
async def test_response_format_fallback_warning(
    provider_config: OpenAICompatProviderConfig,
    mock_response: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test chat completion with response_format triggers fallback and warning."""
    provider = OpenAICompatProvider(config=provider_config)

    request = ChatCompletionRequest(
        model="llama-2-7b",
        messages=[{"role": "user", "content": "Generate JSON"}],
        response_format={"type": "json_object"},  # This should trigger fallback
    )

    with caplog.at_level(logging.WARNING):
        with patch.object(provider._client, "post", new_callable=AsyncMock) as mock_post:
            mock_http_response = Mock(spec=httpx.Response)
            mock_http_response.json.return_value = mock_response
            mock_http_response.raise_for_status = Mock()
            mock_post.return_value = mock_http_response

            response = await provider.chat_completion(request)

            # Verify response_format was NOT sent to the server (fallback)
            payload = mock_post.call_args[1]["json"]
            assert "response_format" not in payload

            # Verify warning was logged
            assert len(caplog.records) > 0
            assert any(
                "response_format is not supported" in record.message for record in caplog.records
            )
            assert any(
                "Falling back to standard chat completion" in record.message
                for record in caplog.records
            )

            # Verify response is still valid
            assert response.id == "chatcmpl-123"

    await provider.close()


@pytest.mark.asyncio
async def test_streaming_fallback_warning(
    provider_config: OpenAICompatProviderConfig,
    mock_response: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that streaming request triggers fallback and warning (P1 fix)."""
    provider = OpenAICompatProvider(config=provider_config)

    request = ChatCompletionRequest(
        model="llama-2-7b",
        messages=[{"role": "user", "content": "Hello"}],
        stream=True,  # This should trigger fallback
    )

    with caplog.at_level(logging.WARNING):
        with patch.object(provider._client, "post", new_callable=AsyncMock) as mock_post:
            mock_http_response = Mock(spec=httpx.Response)
            mock_http_response.json.return_value = mock_response
            mock_http_response.raise_for_status = Mock()
            mock_post.return_value = mock_http_response

            await provider.chat_completion(request)

            # Verify stream was NOT sent to the server (fallback)
            payload = mock_post.call_args[1]["json"]
            assert "stream" not in payload

            # Verify warning was logged
            warning_messages = [record.message for record in caplog.records]
            assert any("Streaming is not supported" in msg for msg in warning_messages)
            assert any("non-streaming chat completion" in msg for msg in warning_messages)

    await provider.close()


@pytest.mark.asyncio
async def test_structured_response_format_fallback(
    provider_config: OpenAICompatProviderConfig,
    mock_response: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that structured response_format with schema triggers fallback."""
    provider = OpenAICompatProvider(config=provider_config)

    request = ChatCompletionRequest(
        model="llama-2-7b",
        messages=[{"role": "user", "content": "Extract data"}],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "user_data",
                "schema": {"type": "object", "properties": {"name": {"type": "string"}}},
            },
        },
    )

    with caplog.at_level(logging.WARNING):
        with patch.object(provider._client, "post", new_callable=AsyncMock) as mock_post:
            mock_http_response = Mock(spec=httpx.Response)
            mock_http_response.json.return_value = mock_response
            mock_http_response.raise_for_status = Mock()
            mock_post.return_value = mock_http_response

            await provider.chat_completion(request)

            # Verify response_format was stripped
            payload = mock_post.call_args[1]["json"]
            assert "response_format" not in payload

            # Verify warning suggests alternative
            warning_messages = [record.message for record in caplog.records]
            assert any("system message" in msg for msg in warning_messages)

    await provider.close()


@pytest.mark.asyncio
async def test_provider_with_api_key() -> None:
    """Test that API key is included in headers when configured."""
    config = OpenAICompatProviderConfig(api_key="secret-key")
    provider = OpenAICompatProvider(config=config)

    headers = provider._build_headers()
    assert "Authorization" in headers
    assert headers["Authorization"] == "Bearer secret-key"

    await provider.close()


@pytest.mark.asyncio
async def test_provider_without_api_key() -> None:
    """Test that Authorization header is omitted when no API key."""
    config = OpenAICompatProviderConfig(api_key=None)
    provider = OpenAICompatProvider(config=config)

    headers = provider._build_headers()
    assert "Authorization" not in headers
    assert headers["Content-Type"] == "application/json"

    await provider.close()


@pytest.mark.asyncio
async def test_provider_default_config() -> None:
    """Test provider with default configuration."""
    provider = OpenAICompatProvider()

    assert provider.config.base_url == "http://localhost:8000/v1/"
    assert provider.config.timeout == 3.0  # Reduced for fast failure when server unavailable
    assert provider.config.api_key is None

    await provider.close()


@pytest.mark.asyncio
async def test_provider_context_manager(
    provider_config: OpenAICompatProviderConfig,
) -> None:
    """Test provider as async context manager."""
    async with OpenAICompatProvider(config=provider_config) as provider:
        assert provider is not None
        capabilities = provider.get_capabilities()
        assert capabilities.supports_chat is True

    # Client should be closed after context exit


@pytest.mark.asyncio
async def test_http_error_handling(
    provider_config: OpenAICompatProviderConfig,
) -> None:
    """Test that HTTP errors are properly raised."""
    provider = OpenAICompatProvider(config=provider_config)

    request = ChatCompletionRequest(
        model="invalid-model", messages=[{"role": "user", "content": "test"}]
    )

    with patch.object(provider._client, "post", new_callable=AsyncMock) as mock_post:
        mock_http_response = Mock(spec=httpx.Response)
        mock_http_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=Mock(), response=Mock()
        )
        mock_post.return_value = mock_http_response

        with pytest.raises(httpx.HTTPStatusError):
            await provider.chat_completion(request)

    await provider.close()


@pytest.mark.asyncio
async def test_multiple_fallbacks(
    provider_config: OpenAICompatProviderConfig,
    mock_response: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test multiple unsupported features trigger multiple warnings."""
    provider = OpenAICompatProvider(config=provider_config)

    request = ChatCompletionRequest(
        model="llama-2-7b",
        messages=[{"role": "user", "content": "Test"}],
        response_format={"type": "json_object"},
        stream=True,
    )

    with caplog.at_level(logging.WARNING):
        with patch.object(provider._client, "post", new_callable=AsyncMock) as mock_post:
            mock_http_response = Mock(spec=httpx.Response)
            mock_http_response.json.return_value = mock_response
            mock_http_response.raise_for_status = Mock()
            mock_post.return_value = mock_http_response

            await provider.chat_completion(request)

            # Verify both unsupported features were stripped
            payload = mock_post.call_args[1]["json"]
            assert "stream" not in payload
            assert "response_format" not in payload

            # Verify both warnings were logged
            warning_messages = [record.message for record in caplog.records]
            assert any("Streaming is not supported" in msg for msg in warning_messages)
            assert any("response_format is not supported" in msg for msg in warning_messages)
            assert len(caplog.records) >= 2

    await provider.close()


def test_generate_returns_llmresponse(
    provider_config: OpenAICompatProviderConfig, mock_response: dict[str, Any]
) -> None:
    """generate() should wrap chat completion output into LLMResponse."""
    provider = OpenAICompatProvider(config=provider_config)
    chat_response = ChatCompletionResponse(**mock_response)

    with patch.object(provider, "_run_chat_completion", return_value=chat_response):
        result = provider.generate("Hello", model="llama-2-7b")

    assert isinstance(result, LLMResponse)
    assert result.content == "Hello!"
    assert result.metadata["endpoint"] == "chat_completions"
    assert result.response_format_ok is True

    asyncio.run(provider.close())


def test_generate_with_unsupported_response_format_logs_warning(
    provider_config: OpenAICompatProviderConfig,
    mock_response: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Requesting structured outputs should emit warning when unsupported."""
    provider = OpenAICompatProvider(config=provider_config)
    chat_response = ChatCompletionResponse(**mock_response)

    with patch.object(provider, "_run_chat_completion", return_value=chat_response):
        with caplog.at_level(logging.WARNING):
            result = provider.generate(
                "Give JSON",
                model="llama-2-7b",
                response_format={"type": "json_schema"},
            )

    assert result.response_format_ok is False
    assert any(
        "Structured response_format is not supported" in record.message for record in caplog.records
    )

    asyncio.run(provider.close())
