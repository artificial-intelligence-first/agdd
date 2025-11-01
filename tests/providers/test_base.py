"""Tests for LLM provider base abstractions."""

from __future__ import annotations

from typing import Any


from magsag.providers.base import BaseLLMProvider, LLMResponse


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_minimal_response(self) -> None:
        """Test creating a minimal LLMResponse."""
        response = LLMResponse(
            content="Hello, world!",
            model="gpt-4",
            input_tokens=10,
            output_tokens=5,
        )

        assert response.content == "Hello, world!"
        assert response.model == "gpt-4"
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.tool_calls is None
        assert response.response_format_ok is True
        assert response.raw_output_blocks is None
        assert response.metadata == {}

    def test_response_with_tool_calls(self) -> None:
        """Test LLMResponse with tool calls."""
        tool_calls: list[dict[str, Any]] = [
            {
                "id": "call_123",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"location": "Tokyo"}'},
            }
        ]

        response = LLMResponse(
            content="",
            model="gpt-4",
            input_tokens=20,
            output_tokens=15,
            tool_calls=tool_calls,
        )

        assert response.tool_calls == tool_calls
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["function"]["name"] == "get_weather"

    def test_response_with_format_validation(self) -> None:
        """Test LLMResponse with format validation status."""
        response = LLMResponse(
            content='{"status": "ok"}',
            model="gpt-4",
            input_tokens=10,
            output_tokens=8,
            response_format_ok=True,
        )

        assert response.response_format_ok is True

        failed_response = LLMResponse(
            content="invalid json",
            model="gpt-4",
            input_tokens=10,
            output_tokens=8,
            response_format_ok=False,
        )

        assert failed_response.response_format_ok is False

    def test_response_with_raw_output_blocks(self) -> None:
        """Test LLMResponse with raw output blocks."""
        raw_blocks: list[dict[str, Any]] = [
            {"type": "text", "text": "Hello"},
            {"type": "tool_use", "id": "call_456", "name": "calculator", "input": {"expr": "2+2"}},
        ]

        response = LLMResponse(
            content="Hello",
            model="claude-3-opus",
            input_tokens=10,
            output_tokens=5,
            raw_output_blocks=raw_blocks,
        )

        assert response.raw_output_blocks == raw_blocks
        assert len(response.raw_output_blocks) == 2

    def test_response_with_metadata(self) -> None:
        """Test LLMResponse with additional metadata."""
        metadata: dict[str, Any] = {
            "finish_reason": "stop",
            "system_fingerprint": "fp_123",
            "logprobs": None,
        }

        response = LLMResponse(
            content="Test",
            model="gpt-4",
            input_tokens=5,
            output_tokens=3,
            metadata=metadata,
        )

        assert response.metadata == metadata
        assert response.metadata["finish_reason"] == "stop"

    def test_response_all_fields(self) -> None:
        """Test LLMResponse with all fields populated."""
        response = LLMResponse(
            content="Complete response",
            model="gpt-4-turbo",
            input_tokens=100,
            output_tokens=50,
            tool_calls=[{"id": "call_789", "type": "function"}],
            response_format_ok=True,
            raw_output_blocks=[{"type": "text", "text": "Complete response"}],
            metadata={"finish_reason": "stop", "custom_field": "value"},
        )

        assert response.content == "Complete response"
        assert response.model == "gpt-4-turbo"
        assert response.input_tokens == 100
        assert response.output_tokens == 50
        assert response.tool_calls is not None
        assert response.response_format_ok is True
        assert response.raw_output_blocks is not None
        assert "custom_field" in response.metadata


class MockLLMProvider:
    """Mock implementation of BaseLLMProvider for testing."""

    def generate(
        self,
        prompt: str,
        *,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        response_format: dict[str, Any] | None = None,
        reasoning: dict[str, Any] | None = None,
        mcp_tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Mock generate method."""
        return LLMResponse(
            content=f"Mock response to: {prompt}",
            model=model,
            input_tokens=len(prompt.split()),
            output_tokens=5,
            tool_calls=tools if tools else None,
            metadata={
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tool_choice": tool_choice,
                "response_format": response_format,
                "reasoning": reasoning,
                "mcp_tools": mcp_tools,
                **kwargs,
            },
        )

    def get_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Mock get_cost method."""
        # Simple mock pricing: $0.01 per 1000 tokens
        return (input_tokens + output_tokens) * 0.01 / 1000


class TestBaseLLMProvider:
    """Tests for BaseLLMProvider protocol."""

    def test_provider_implements_protocol(self) -> None:
        """Test that MockLLMProvider implements BaseLLMProvider protocol."""
        provider: BaseLLMProvider = MockLLMProvider()

        # Should not raise any type errors
        assert hasattr(provider, "generate")
        assert hasattr(provider, "get_cost")

    def test_generate_basic(self) -> None:
        """Test basic generate call."""
        provider = MockLLMProvider()
        response = provider.generate("Hello", model="gpt-4")

        assert response.content == "Mock response to: Hello"
        assert response.model == "gpt-4"
        assert response.input_tokens == 1
        assert response.output_tokens == 5

    def test_generate_with_tools(self) -> None:
        """Test generate with tool definitions."""
        provider = MockLLMProvider()
        tools: list[dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                    },
                },
            }
        ]

        response = provider.generate("What's the weather?", model="gpt-4", tools=tools)

        assert response.tool_calls == tools
        assert response.metadata["tool_choice"] is None

    def test_generate_with_tool_choice(self) -> None:
        """Test generate with tool_choice parameter."""
        provider = MockLLMProvider()

        # String tool choice
        response = provider.generate("Test", model="gpt-4", tool_choice="auto")
        assert response.metadata["tool_choice"] == "auto"

        # Dict tool choice
        tool_choice_dict: dict[str, Any] = {
            "type": "function",
            "function": {"name": "specific_tool"},
        }
        response = provider.generate("Test", model="gpt-4", tool_choice=tool_choice_dict)
        assert response.metadata["tool_choice"] == tool_choice_dict

    def test_generate_with_response_format(self) -> None:
        """Test generate with response_format parameter."""
        provider = MockLLMProvider()
        response_format: dict[str, Any] = {"type": "json_object"}

        response = provider.generate("Test", model="gpt-4", response_format=response_format)

        assert response.metadata["response_format"] == response_format

    def test_generate_with_reasoning(self) -> None:
        """Test generate with reasoning parameter."""
        provider = MockLLMProvider()
        reasoning_config: dict[str, Any] = {"mode": "extended", "budget_tokens": 1000}

        response = provider.generate("Test", model="gpt-4", reasoning=reasoning_config)

        assert response.metadata["reasoning"] == reasoning_config

    def test_generate_with_mcp_tools(self) -> None:
        """Test generate with MCP tools parameter."""
        provider = MockLLMProvider()
        mcp_tools: list[dict[str, Any]] = [
            {"name": "mcp_tool_1", "description": "MCP tool", "input_schema": {}}
        ]

        response = provider.generate("Test", model="gpt-4", mcp_tools=mcp_tools)

        assert response.metadata["mcp_tools"] == mcp_tools

    def test_generate_with_all_parameters(self) -> None:
        """Test generate with all optional parameters."""
        provider = MockLLMProvider()
        tools: list[dict[str, Any]] = [{"type": "function", "function": {"name": "tool1"}}]
        tool_choice: str = "required"
        response_format: dict[str, Any] = {"type": "json_schema", "schema": {}}
        reasoning: dict[str, Any] = {"mode": "extended"}
        mcp_tools: list[dict[str, Any]] = [{"name": "mcp_tool"}]

        response = provider.generate(
            "Complex prompt",
            model="gpt-4-turbo",
            max_tokens=2000,
            temperature=0.5,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            reasoning=reasoning,
            mcp_tools=mcp_tools,
            custom_param="custom_value",
        )

        assert response.content == "Mock response to: Complex prompt"
        assert response.model == "gpt-4-turbo"
        assert response.metadata["temperature"] == 0.5
        assert response.metadata["max_tokens"] == 2000
        assert response.metadata["tool_choice"] == tool_choice
        assert response.metadata["response_format"] == response_format
        assert response.metadata["reasoning"] == reasoning
        assert response.metadata["mcp_tools"] == mcp_tools
        assert response.metadata["custom_param"] == "custom_value"

    def test_get_cost_synchronous(self) -> None:
        """Test that get_cost is a synchronous function."""
        provider = MockLLMProvider()

        # Should work without await
        cost = provider.get_cost("gpt-4", input_tokens=1000, output_tokens=500)

        assert isinstance(cost, float)
        assert cost > 0
        assert cost == (1000 + 500) * 0.01 / 1000

    def test_get_cost_calculation(self) -> None:
        """Test cost calculation with different token counts."""
        provider = MockLLMProvider()

        cost1 = provider.get_cost("gpt-4", input_tokens=100, output_tokens=50)
        cost2 = provider.get_cost("gpt-4", input_tokens=1000, output_tokens=500)

        assert cost2 > cost1
        assert cost1 == 150 * 0.01 / 1000
        assert cost2 == 1500 * 0.01 / 1000


class TestProtocolCompliance:
    """Tests for protocol compliance and type safety."""

    def test_protocol_type_checking(self) -> None:
        """Test that type checking works correctly with the protocol."""
        provider: BaseLLMProvider = MockLLMProvider()

        # This should type-check correctly
        response: LLMResponse = provider.generate("test", model="gpt-4")
        cost: float = provider.get_cost("gpt-4", 100, 50)

        assert isinstance(response, LLMResponse)
        assert isinstance(cost, float)

    def test_response_dataclass_slots(self) -> None:
        """Test that LLMResponse uses slots for memory efficiency."""
        response = LLMResponse(content="test", model="gpt-4", input_tokens=10, output_tokens=5)

        # Dataclasses with slots=True should not have __dict__
        assert not hasattr(response, "__dict__")
        assert hasattr(response, "__slots__")
