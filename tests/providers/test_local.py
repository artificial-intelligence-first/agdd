"""Tests for LocalProvider with fallback behavior."""

import logging
from typing import Any
from unittest.mock import Mock, patch

import httpx
import pytest

from agdd.providers.base import ChatCompletionRequest, ProviderCapabilities
from agdd.providers.local import LocalProvider, LocalProviderConfig


@pytest.fixture
def provider_config() -> LocalProviderConfig:
    """Create test provider configuration."""
    return LocalProviderConfig(
        base_url="http://localhost:8000/v1",
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
async def test_local_provider_capabilities(provider_config: LocalProviderConfig) -> None:
    """Test that LocalProvider reports correct capabilities."""
    provider = LocalProvider(config=provider_config)
    capabilities = provider.get_capabilities()

    assert isinstance(capabilities, ProviderCapabilities)
    assert capabilities.supports_chat is True
    assert capabilities.supports_responses is False
    assert capabilities.supports_streaming is True
    assert capabilities.supports_function_calling is False

    await provider.close()


@pytest.mark.asyncio
async def test_basic_chat_completion_no_fallback(
    provider_config: LocalProviderConfig, mock_response: dict[str, Any]
) -> None:
    """Test basic chat completion without fallback (no response_format)."""
    provider = LocalProvider(config=provider_config)

    request = ChatCompletionRequest(
        model="llama-2-7b",
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.7,
        max_tokens=100,
    )

    # Mock the HTTP client
    with patch.object(provider._client, "post") as mock_post:
        mock_http_response = Mock(spec=httpx.Response)
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = Mock()
        mock_post.return_value = mock_http_response

        response = await provider.chat_completion(request)

        # Verify request was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/chat/completions"

        # Verify payload does not contain response_format
        payload = call_args[1]["json"]
        assert "response_format" not in payload
        assert payload["model"] == "llama-2-7b"
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 100

        # Verify response
        assert response.id == "chatcmpl-123"
        assert response.model == "llama-2-7b"
        assert len(response.choices) == 1

    await provider.close()


@pytest.mark.asyncio
async def test_chat_completion_with_fallback_warning(
    provider_config: LocalProviderConfig,
    mock_response: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test chat completion with response_format triggers fallback and warning."""
    provider = LocalProvider(config=provider_config)

    request = ChatCompletionRequest(
        model="llama-2-7b",
        messages=[{"role": "user", "content": "Generate JSON"}],
        response_format={"type": "json_object"},  # This should trigger fallback
    )

    with caplog.at_level(logging.WARNING):
        with patch.object(provider._client, "post") as mock_post:
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
async def test_structured_response_format_fallback(
    provider_config: LocalProviderConfig,
    mock_response: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that structured response_format with schema triggers fallback."""
    provider = LocalProvider(config=provider_config)

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
        with patch.object(provider._client, "post") as mock_post:
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
    config = LocalProviderConfig(api_key="secret-key")
    provider = LocalProvider(config=config)

    headers = provider._build_headers()
    assert "Authorization" in headers
    assert headers["Authorization"] == "Bearer secret-key"

    await provider.close()


@pytest.mark.asyncio
async def test_provider_without_api_key() -> None:
    """Test that Authorization header is omitted when no API key."""
    config = LocalProviderConfig(api_key=None)
    provider = LocalProvider(config=config)

    headers = provider._build_headers()
    assert "Authorization" not in headers
    assert headers["Content-Type"] == "application/json"

    await provider.close()


@pytest.mark.asyncio
async def test_provider_default_config() -> None:
    """Test provider with default configuration."""
    provider = LocalProvider()

    assert provider.config.base_url == "http://localhost:8000/v1"
    assert provider.config.timeout == 60.0
    assert provider.config.api_key is None

    await provider.close()


@pytest.mark.asyncio
async def test_provider_context_manager(provider_config: LocalProviderConfig) -> None:
    """Test provider as async context manager."""
    async with LocalProvider(config=provider_config) as provider:
        assert provider is not None
        capabilities = provider.get_capabilities()
        assert capabilities.supports_chat is True

    # Client should be closed after context exit
    # We can't directly test this without implementation details,
    # but we verify no errors occur


@pytest.mark.asyncio
async def test_http_error_handling(
    provider_config: LocalProviderConfig,
) -> None:
    """Test that HTTP errors are properly raised."""
    provider = LocalProvider(config=provider_config)

    request = ChatCompletionRequest(
        model="invalid-model", messages=[{"role": "user", "content": "test"}]
    )

    with patch.object(provider._client, "post") as mock_post:
        mock_http_response = Mock(spec=httpx.Response)
        mock_http_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=Mock(), response=Mock()
        )
        mock_post.return_value = mock_http_response

        with pytest.raises(httpx.HTTPStatusError):
            await provider.chat_completion(request)

    await provider.close()


@pytest.mark.asyncio
async def test_stream_parameter_passthrough(
    provider_config: LocalProviderConfig, mock_response: dict[str, Any]
) -> None:
    """Test that stream parameter is correctly passed through."""
    provider = LocalProvider(config=provider_config)

    request = ChatCompletionRequest(
        model="llama-2-7b",
        messages=[{"role": "user", "content": "Hello"}],
        stream=True,
    )

    with patch.object(provider._client, "post") as mock_post:
        mock_http_response = Mock(spec=httpx.Response)
        mock_http_response.json.return_value = mock_response
        mock_http_response.raise_for_status = Mock()
        mock_post.return_value = mock_http_response

        await provider.chat_completion(request)

        payload = mock_post.call_args[1]["json"]
        assert payload["stream"] is True

    await provider.close()
