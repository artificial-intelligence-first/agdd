"""
Tests for OpenAI Provider with Responses API.

Tests cover:
- Responses API (default)
- Chat Completions API (fallback)
- Streaming
- Tool calling
- Structured outputs
- Error handling
- Cost calculation
"""

from __future__ import annotations

import os
from typing import Iterator

import pytest

from agdd.providers.openai import (
    APIEndpoint,
    CompletionRequest,
    CompletionResponse,
    OpenAIProvider,
    ProviderConfig,
    create_provider,
)

# Skip all tests if OPENAI_API_KEY is not set
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"
)


@pytest.fixture
def provider() -> OpenAIProvider:
    """Create provider with default Responses API"""
    return create_provider()


@pytest.fixture
def chat_provider() -> OpenAIProvider:
    """Create provider with Chat Completions fallback"""
    return create_provider(preferred_endpoint=APIEndpoint.CHAT_COMPLETIONS)


class TestResponsesAPI:
    """Test Responses API (default endpoint)"""

    def test_basic_completion(self, provider: OpenAIProvider) -> None:
        """Test basic completion with Responses API"""
        request = CompletionRequest(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say 'Hello, World!' and nothing else."}],
            temperature=0.0,
            max_tokens=50,
        )

        response = provider.complete(request)
        assert isinstance(response, CompletionResponse)
        assert response.endpoint_used == APIEndpoint.RESPONSES
        assert response.content is not None
        assert "Hello" in response.content
        assert response.usage.total_tokens > 0
        assert response.usage.total_cost_usd > 0

    def test_streaming_completion(self, provider: OpenAIProvider) -> None:
        """Test streaming completion with Responses API"""
        request = CompletionRequest(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Count from 1 to 5."}],
            temperature=0.0,
            stream=True,
        )

        response = provider.complete(request)
        assert isinstance(response, Iterator)

        chunks = list(response)
        assert len(chunks) > 0

        # Check that all chunks use RESPONSES endpoint
        for chunk in chunks:
            assert chunk.endpoint_used == APIEndpoint.RESPONSES

        # Last chunk should have complete content
        final_chunk = chunks[-1]
        assert final_chunk.content is not None
        assert len(final_chunk.content) > 0

    def test_tool_calling(self, provider: OpenAIProvider) -> None:
        """Test tool calling with Responses API"""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "City name",
                            },
                            "unit": {
                                "type": "string",
                                "enum": ["celsius", "fahrenheit"],
                            },
                        },
                        "required": ["location"],
                    },
                },
            }
        ]

        request = CompletionRequest(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "What's the weather in Tokyo?"}],
            tools=tools,
            tool_choice="auto",
            temperature=0.0,
        )

        response = provider.complete(request)
        assert isinstance(response, CompletionResponse)
        assert response.endpoint_used == APIEndpoint.RESPONSES

        # Should have tool calls
        assert len(response.tool_calls) > 0
        tool_call = response.tool_calls[0]
        assert tool_call["function"]["name"] == "get_weather"

    def test_structured_output(self, provider: OpenAIProvider) -> None:
        """Test structured output with response_format"""
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "person_info",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "age": {"type": "number"},
                    },
                    "required": ["name", "age"],
                    "additionalProperties": False,
                },
            },
        }

        request = CompletionRequest(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": "Return JSON for: Alice is 30 years old.",
                }
            ],
            response_format=response_format,
            temperature=0.0,
        )

        response = provider.complete(request)
        assert isinstance(response, CompletionResponse)
        assert response.endpoint_used == APIEndpoint.RESPONSES
        assert response.content is not None

        # Should be valid JSON matching schema
        import json

        data = json.loads(response.content)
        assert "name" in data
        assert "age" in data


class TestChatCompletionsAPI:
    """Test Chat Completions API (fallback endpoint)"""

    def test_basic_completion(self, chat_provider: OpenAIProvider) -> None:
        """Test basic completion with Chat Completions API"""
        request = CompletionRequest(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say 'Hello, World!' and nothing else."}],
            temperature=0.0,
            max_tokens=50,
        )

        response = chat_provider.complete(request)
        assert isinstance(response, CompletionResponse)
        assert response.endpoint_used == APIEndpoint.CHAT_COMPLETIONS
        assert response.content is not None
        assert "Hello" in response.content
        assert response.usage.total_tokens > 0

    def test_streaming_completion(self, chat_provider: OpenAIProvider) -> None:
        """Test streaming with Chat Completions API"""
        request = CompletionRequest(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Count from 1 to 3."}],
            temperature=0.0,
            stream=True,
        )

        response = chat_provider.complete(request)
        assert isinstance(response, Iterator)

        chunks = list(response)
        assert len(chunks) > 0

        for chunk in chunks:
            assert chunk.endpoint_used == APIEndpoint.CHAT_COMPLETIONS


class TestCostCalculation:
    """Test cost calculation and usage tracking"""

    def test_usage_tracking(self, provider: OpenAIProvider) -> None:
        """Test that usage is properly tracked"""
        request = CompletionRequest(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say hello."}],
            temperature=0.0,
        )

        response = provider.complete(request)
        assert isinstance(response, CompletionResponse)

        usage = response.usage
        assert usage.prompt_tokens > 0
        assert usage.completion_tokens > 0
        assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens
        assert usage.prompt_cost_usd > 0
        assert usage.completion_cost_usd > 0
        assert usage.total_cost_usd == usage.prompt_cost_usd + usage.completion_cost_usd

    def test_custom_pricing(self) -> None:
        """Test custom pricing configuration"""
        custom_pricing = {
            "gpt-4o-mini": {"prompt": 1.0, "completion": 2.0}  # Custom prices
        }
        config = ProviderConfig(pricing=custom_pricing)
        provider = OpenAIProvider(config)

        # Calculate cost manually
        usage = provider._calculate_cost("gpt-4o-mini", 1000, 500)
        expected_prompt_cost = (1000 / 1_000_000) * 1.0
        expected_completion_cost = (500 / 1_000_000) * 2.0

        assert abs(usage.prompt_cost_usd - expected_prompt_cost) < 0.000001
        assert abs(usage.completion_cost_usd - expected_completion_cost) < 0.000001


class TestErrorHandling:
    """Test error handling"""

    def test_invalid_model(self, provider: OpenAIProvider) -> None:
        """Test handling of invalid model"""
        request = CompletionRequest(
            model="invalid-model-name",
            messages=[{"role": "user", "content": "Hello"}],
        )

        with pytest.raises(Exception):  # OpenAI API will raise error
            provider.complete(request)

    def test_missing_api_key() -> None:
        """Test handling of missing API key"""
        config = ProviderConfig(api_key=None)

        # Temporarily remove env var
        original_key = os.environ.get("OPENAI_API_KEY")
        if original_key:
            del os.environ["OPENAI_API_KEY"]

        try:
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                config.get_api_key()
        finally:
            # Restore env var
            if original_key:
                os.environ["OPENAI_API_KEY"] = original_key


class TestProviderFactory:
    """Test provider factory function"""

    def test_create_with_defaults(self) -> None:
        """Test creating provider with defaults"""
        provider = create_provider()
        assert provider.config.preferred_endpoint == APIEndpoint.RESPONSES

    def test_create_with_chat_completions(self) -> None:
        """Test creating provider with chat completions"""
        provider = create_provider(preferred_endpoint=APIEndpoint.CHAT_COMPLETIONS)
        assert provider.config.preferred_endpoint == APIEndpoint.CHAT_COMPLETIONS

    def test_create_with_custom_config(self) -> None:
        """Test creating provider with custom config"""
        provider = create_provider(timeout=120.0, max_retries=5)
        assert provider.config.timeout == 120.0
        assert provider.config.max_retries == 5


# Integration test combining multiple features
class TestIntegration:
    """Integration tests combining multiple features"""

    def test_responses_with_tools_and_streaming(self, provider: OpenAIProvider) -> None:
        """Test Responses API with tools in streaming mode"""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculate",
                    "description": "Perform calculation",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"},
                        },
                        "required": ["expression"],
                    },
                },
            }
        ]

        request = CompletionRequest(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "What is 2 + 2?"}],
            tools=tools,
            stream=True,
            temperature=0.0,
        )

        response = provider.complete(request)
        assert isinstance(response, Iterator)

        chunks = list(response)
        assert len(chunks) > 0

        # Verify all chunks are from RESPONSES endpoint
        for chunk in chunks:
            assert chunk.endpoint_used == APIEndpoint.RESPONSES
