"""Mock LLM provider for testing without external dependencies."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from magsag.providers.base import LLMResponse

logger = logging.getLogger(__name__)


class MockLLMProvider:
    """Mock LLM provider that returns predictable responses for testing.

    This provider is designed for testing and does not make any external API calls.
    It returns structured, deterministic responses based on the prompt content.
    """

    def __init__(self) -> None:
        """Initialize mock provider."""
        self._call_count = 0
        logger.info("MockLLMProvider initialized (no external calls will be made)")

    def generate(
        self,
        prompt: str,
        *,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str | dict[str, Any]] = None,
        response_format: Optional[dict[str, Any]] = None,
        reasoning: Optional[dict[str, Any]] = None,
        mcp_tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a mock response based on prompt content.

        Args:
            prompt: Input prompt (analyzed for content-based responses)
            model: Model identifier (logged but not used)
            max_tokens: Maximum tokens (logged but not used)
            temperature: Sampling temperature (logged but not used)
            tools: Tool definitions (triggers tool call response if present)
            tool_choice: Tool selection preference
            response_format: Response format specification
            reasoning: Reasoning configuration
            mcp_tools: MCP tool definitions
            **kwargs: Additional parameters (ignored)

        Returns:
            LLMResponse with mock content and metadata
        """
        self._call_count += 1

        # Generate response based on context
        if tools or mcp_tools:
            # Return a tool call response
            content = self._generate_tool_call_response(prompt, tools or mcp_tools or [])
        elif response_format and response_format.get("type") == "json_object":
            # Return structured JSON
            content = self._generate_json_response(prompt)
        else:
            # Return plain text
            content = self._generate_text_response(prompt)

        prompt_tokens = len(prompt.split())
        completion_tokens = len(content.split())

        return LLMResponse(
            content=content,
            model=model,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            metadata={
                "provider": "mock",
                "call_count": self._call_count,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )

    def _generate_text_response(self, prompt: str) -> str:
        """Generate a plain text mock response."""
        # Extract context from prompt for more realistic responses
        if "compensation" in prompt.lower() or "salary" in prompt.lower():
            return (
                "Based on the candidate profile, I recommend the following compensation package:\n"
                "- Base Salary: $150,000\n"
                "- Sign-on Bonus: $25,000\n"
                "- Annual Bonus Target: 15%\n"
                "- Equity: 10,000 RSUs vesting over 4 years"
            )
        elif "offer" in prompt.lower():
            return (
                "I have generated a comprehensive offer packet including:\n"
                "1. Compensation details\n"
                "2. Benefits overview\n"
                "3. Role responsibilities\n"
                "4. Start date and logistics"
            )
        else:
            return f"Mock response to prompt (length: {len(prompt)} chars)"

    def _generate_json_response(self, prompt: str) -> str:
        """Generate a structured JSON mock response."""
        # Return realistic structured data
        if "compensation" in prompt.lower() or "salary" in prompt.lower():
            data = {
                "role": "Software Engineer",
                "band": "L4",
                "base_salary": {"amount": 150000, "currency": "USD"},
                "sign_on_bonus": {"amount": 25000, "currency": "USD"},
                "annual_bonus_target": 0.15,
                "equity": {"shares": 10000, "vesting_years": 4},
            }
        else:
            data = {
                "status": "success",
                "message": "Mock structured response",
                "data": {"prompt_length": len(prompt)},
            }
        return json.dumps(data, indent=2)

    def _generate_tool_call_response(self, prompt: str, tools: list[dict[str, Any]]) -> str:
        """Generate a mock tool call response."""
        if not tools:
            return self._generate_text_response(prompt)

        # Select first tool and generate a mock call
        tool = tools[0]
        tool_name = tool.get("function", {}).get("name", "unknown_tool")

        tool_call = {
            "id": f"call_mock_{self._call_count}",
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps({"query": "mock query", "param": "value"}),
            },
        }

        return json.dumps(
            {
                "tool_calls": [tool_call],
                "message": f"Calling tool: {tool_name}",
            }
        )

    def get_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Return zero cost for mock provider."""
        return 0.0

    def close(self) -> None:
        """No-op close for mock provider."""
        pass

    def __enter__(self) -> MockLLMProvider:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
