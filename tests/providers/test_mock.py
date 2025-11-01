"""Tests for MockLLMProvider."""

from magsag.providers.mock import MockLLMProvider


def test_mock_provider_basic() -> None:
    """Test basic mock provider functionality."""
    provider = MockLLMProvider()

    response = provider.generate("test prompt", model="test-model")

    assert response.content
    assert response.model == "test-model"
    assert response.input_tokens > 0
    assert response.output_tokens > 0
    assert response.metadata["provider"] == "mock"
    assert response.metadata["call_count"] == 1


def test_mock_provider_compensation_context() -> None:
    """Test that mock provider returns context-aware compensation responses."""
    provider = MockLLMProvider()

    response = provider.generate(
        "Generate compensation package for Senior Engineer", model="test-model"
    )

    assert "salary" in response.content.lower() or "compensation" in response.content.lower()
    assert "$" in response.content or "USD" in response.content


def test_mock_provider_json_response() -> None:
    """Test JSON response format."""
    provider = MockLLMProvider()

    response = provider.generate(
        "Generate compensation data",
        model="test-model",
        response_format={"type": "json_object"},
    )

    # Should return valid JSON
    assert response.content.startswith("{")
    assert response.content.endswith("}")


def test_mock_provider_tool_calls() -> None:
    """Test tool call responses."""
    provider = MockLLMProvider()

    tools = [
        {
            "function": {
                "name": "get_salary_band",
                "description": "Get salary band for role",
            }
        }
    ]

    response = provider.generate("Get salary band", model="test-model", tools=tools)

    # Should return tool call structure
    assert "tool_call" in response.content.lower() or "function" in response.content.lower()


def test_mock_provider_call_count() -> None:
    """Test that call count increments."""
    provider = MockLLMProvider()

    response1 = provider.generate("test 1", model="test-model")
    response2 = provider.generate("test 2", model="test-model")

    assert response1.metadata["call_count"] == 1
    assert response2.metadata["call_count"] == 2


def test_mock_provider_zero_cost() -> None:
    """Test that mock provider has zero cost."""
    provider = MockLLMProvider()

    cost = provider.get_cost("test-model", input_tokens=100, output_tokens=50)

    assert cost == 0.0


def test_mock_provider_context_manager() -> None:
    """Test mock provider as context manager."""
    with MockLLMProvider() as provider:
        response = provider.generate("test", model="test-model")
        assert response.content
