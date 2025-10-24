"""Tests for LocalLLMProvider fallback behavior and error handling."""

from __future__ import annotations

from unittest.mock import ANY, Mock, patch

import httpx
import pytest

from agdd.providers.base import LLMResponse
from agdd.providers.local import LocalLLMProvider, LocalProviderConfig, ResponsesNotSupportedError


@pytest.fixture
def local_config() -> LocalProviderConfig:
    """Provide a default local provider configuration."""
    return LocalProviderConfig(base_url="http://localhost:9999/v1/")


def _make_llm_response() -> LLMResponse:
    return LLMResponse(
        content="Fallback answer",
        model="llama-local",
        input_tokens=5,
        output_tokens=10,
        metadata={"endpoint": "chat_completions"},
    )


def test_responses_success_returns_llmresponse(local_config: LocalProviderConfig) -> None:
    """Successful Responses API call should return parsed LLMResponse."""
    responses_payload = {
        "id": "resp_123",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "Hello from Responses API!"},
                ],
            }
        ],
        "usage": {"input_tokens": 12, "output_tokens": 4},
    }

    mock_http_response = Mock(spec=httpx.Response)
    mock_http_response.json.return_value = responses_payload
    mock_http_response.raise_for_status.return_value = None

    mock_client = Mock(spec=httpx.Client)
    mock_client.post.return_value = mock_http_response

    compat_provider = Mock()
    compat_provider.generate.side_effect = AssertionError("Should not fall back")
    compat_provider.close = Mock()

    with patch("agdd.providers.local.httpx.Client", return_value=mock_client):
        provider = LocalLLMProvider(config=local_config, compat_provider=compat_provider)
        result = provider.generate("Hello!", model="llama-local")
        provider.close()

    assert isinstance(result, LLMResponse)
    assert result.content == "Hello from Responses API!"
    assert result.input_tokens == 12
    assert result.output_tokens == 4
    assert result.metadata["endpoint"] == "responses"
    mock_client.post.assert_called_once_with("responses", json=ANY)


def test_responses_unavailable_falls_back_to_chat(
    local_config: LocalProviderConfig, caplog: pytest.LogCaptureFixture
) -> None:
    """When Responses API is unavailable, provider should fall back gracefully."""
    request = httpx.Request("POST", "http://localhost:9999/v1/responses")
    response = httpx.Response(status_code=404, request=request)
    http_error = httpx.HTTPStatusError("Not found", request=request, response=response)

    mock_client = Mock(spec=httpx.Client)
    mock_client.post.side_effect = http_error

    compat_provider = Mock()
    compat_provider.generate.return_value = _make_llm_response()
    compat_provider.close = Mock()

    with patch("agdd.providers.local.httpx.Client", return_value=mock_client):
        provider = LocalLLMProvider(config=local_config, compat_provider=compat_provider)
        with caplog.at_level("WARNING"):
            result = provider.generate(
                "Return JSON",
                model="llama-local",
                response_format={"type": "json_schema"},
            )
        provider.close()

    compat_provider.generate.assert_called_once()
    assert result.metadata["fallback"] == "chat_completions"
    assert "Downgrading to chat completions" in result.metadata["warnings"][-1]
    assert any("Falling back to chat completions" in record.message for record in caplog.records)


def test_responses_not_supported_error_triggers_fallback(
    local_config: LocalProviderConfig,
) -> None:
    """ResponsesNotSupportedError from responses invocation should trigger fallback."""
    compat_provider = Mock()
    compat_provider.generate.return_value = _make_llm_response()
    compat_provider.close = Mock()

    with patch("agdd.providers.local.httpx.Client"):
        provider = LocalLLMProvider(config=local_config, compat_provider=compat_provider)
        provider._invoke_responses = Mock(side_effect=ResponsesNotSupportedError("unsupported"))  # type: ignore[attr-defined]
        result = provider.generate("Hi", model="llama-local", tools=[{"name": "noop"}])
        provider.close()

    compat_provider.generate.assert_called_once()
    assert result.metadata["fallback"] == "chat_completions"
    assert "unsupported" in result.metadata["warnings"][0]
