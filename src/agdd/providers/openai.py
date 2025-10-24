"""
OpenAI Provider - Responses API implementation with chat.completions fallback.

This provider supports:
- Responses API (primary, recommended)
- Chat Completions API (fallback, policy-switchable)
- Tools, response_format, streaming
- Batch API integration for cost optimization
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterator, Optional, Union, cast

from openai import NOT_GIVEN, NotGiven, OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.responses import Response as OpenAIResponse

from agdd.security.moderation import (
    ContentModerator,
    ModerationResult,
    get_content_moderator,
    result_to_metadata,
)


class APIEndpoint(str, Enum):
    """Supported OpenAI API endpoints"""

    RESPONSES = "responses"
    CHAT_COMPLETIONS = "chat_completions"


@dataclass
class Usage:
    """Token usage and cost tracking"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cost_usd: float = 0.0
    completion_cost_usd: float = 0.0
    total_cost_usd: float = 0.0


@dataclass
class ProviderConfig:
    """OpenAI Provider configuration"""

    api_key: Optional[str] = None
    base_url: Optional[str] = None
    organization: Optional[str] = None
    timeout: float = 60.0
    max_retries: int = 2
    # Policy-driven endpoint selection
    preferred_endpoint: APIEndpoint = APIEndpoint.RESPONSES
    # Model pricing (USD per 1M tokens)
    pricing: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize with default pricing if not provided"""
        if not self.pricing:
            # Default pricing for common models (as of 2025-01)
            # Reference: https://openai.com/api/pricing/
            self.pricing = {
                "gpt-4o": {"prompt": 2.50, "completion": 10.00},
                "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
                "gpt-4-turbo": {"prompt": 10.00, "completion": 30.00},
                "gpt-3.5-turbo": {"prompt": 0.50, "completion": 1.50},
            }

    def get_api_key(self) -> str:
        """Get API key from config or environment"""
        if self.api_key:
            return self.api_key
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY not found in config or environment")
        return key


@dataclass
class CompletionRequest:
    """Unified request for both Responses and Chat Completions APIs"""

    model: str
    messages: list[Dict[str, Any]]
    temperature: float = 1.0
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Union[str, list[str], None, NotGiven] = NOT_GIVEN
    stream: bool = False
    # Structured outputs
    tools: Union[list[Dict[str, Any]], NotGiven] = NOT_GIVEN
    tool_choice: Union[str, Dict[str, Any], NotGiven] = NOT_GIVEN
    response_format: Union[Dict[str, Any], NotGiven] = NOT_GIVEN
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResponse:
    """Unified response from both APIs"""

    id: str
    model: str
    content: Optional[str]
    finish_reason: Optional[str]
    usage: Usage
    tool_calls: list[Dict[str, Any]] = field(default_factory=list)
    raw_response: Any = None
    endpoint_used: APIEndpoint = APIEndpoint.RESPONSES
    moderation: dict[str, Any] | None = None


class OpenAIProvider:
    """
    OpenAI Provider with Responses API support.

    Supports both Responses API (default) and Chat Completions API (fallback).
    Endpoint selection is policy-driven via ProviderConfig.
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        self.config = config or ProviderConfig()
        self.client = OpenAI(
            api_key=self.config.get_api_key(),
            base_url=self.config.base_url,
            organization=self.config.organization,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )

    @staticmethod
    def _extract_texts_from_messages(messages: list[Dict[str, Any]]) -> list[str]:
        texts: list[str] = []
        for message in messages:
            content = message.get("content")
            if isinstance(content, str):
                texts.append(content)
                continue
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    for key in ("text", "input_text", "output_text"):
                        value = block.get(key)
                        if isinstance(value, str):
                            texts.append(value)
        return texts

    def _moderate_request(self, request: CompletionRequest, moderator: ContentModerator) -> None:
        texts = self._extract_texts_from_messages(request.messages)
        if not texts:
            return
        result = moderator.review_texts(
            texts,
            stage="input",
            metadata={"provider": "openai", "model": request.model},
            client=self.client,
        )
        request.metadata.setdefault("moderation", {})["input"] = result_to_metadata(result, "input")

    def _apply_output_moderation(
        self,
        response: CompletionResponse,
        moderator: ContentModerator,
        *,
        stage: str = "output",
    ) -> CompletionResponse:
        if response.content:
            result = moderator.review_texts(
                [response.content],
                stage=stage,
                metadata={"provider": "openai", "model": response.model},
                client=self.client,
            )
        else:
            result = ModerationResult(
                flagged=False, categories=tuple(), raw_response=None, checked=False
            )
        response.moderation = result_to_metadata(result, stage)
        return response

    def _wrap_stream_with_moderation(
        self,
        iterator: Iterator[CompletionResponse],
        moderator: ContentModerator,
        *,
        model: str,
    ) -> Iterator[CompletionResponse]:
        accumulated = ""
        for response in iterator:
            if response.content:
                accumulated += response.content
                result = moderator.review_texts(
                    [accumulated],
                    stage="output_stream",
                    metadata={"provider": "openai", "model": model, "stream": True},
                    client=self.client,
                )
                response.moderation = result_to_metadata(result, "output_stream")
            yield response

    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> Usage:
        """Calculate usage and cost based on token counts"""
        pricing = self.config.pricing.get(model, {"prompt": 0.0, "completion": 0.0})
        prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]

        return Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            prompt_cost_usd=prompt_cost,
            completion_cost_usd=completion_cost,
            total_cost_usd=prompt_cost + completion_cost,
        )

    def _responses_api_complete(self, request: CompletionRequest) -> CompletionResponse:
        """Execute request using Responses API"""
        # Build API parameters - Responses API uses different structure
        # Convert messages to input format for Responses API
        input_items = []
        for msg in request.messages:
            input_items.append(
                {
                    "type": "message",
                    "role": msg.get("role", "user"),
                    "content": [{"type": "input_text", "text": msg.get("content", "")}],
                }
            )

        params: Dict[str, Any] = {
            "model": request.model,
            "input": input_items,
            "temperature": request.temperature,
            "top_p": request.top_p,
        }

        if request.max_tokens is not None:
            params["max_output_tokens"] = request.max_tokens
        if not isinstance(request.tools, NotGiven):
            params["tools"] = request.tools
        if not isinstance(request.tool_choice, NotGiven):
            params["tool_choice"] = request.tool_choice
        if not isinstance(request.response_format, NotGiven):
            # Responses API uses response_format for structured outputs
            params["response_format"] = request.response_format
        if request.metadata:
            params["metadata"] = request.metadata

        # Call Responses API
        response = self.client.responses.create(**params)
        response = cast(OpenAIResponse, response)

        # Extract content and tool calls from output
        content = None
        tool_calls_list: list[Dict[str, Any]] = []

        # Responses API uses different structure - check text field first
        if response.text:
            content = response.text.text if hasattr(response.text, "text") else str(response.text)

        # Check output items for tool calls
        if response.output:
            for item in response.output:
                if hasattr(item, "type"):
                    if item.type == "message":
                        if hasattr(item, "content"):
                            for content_part in item.content:
                                if hasattr(content_part, "text"):
                                    content = content_part.text
                    elif item.type in ["function_call", "tool_call"]:
                        # Extract tool call information
                        tool_calls_list.append(
                            {
                                "id": getattr(item, "id", ""),
                                "type": "function",
                                "function": {
                                    "name": getattr(item, "name", ""),
                                    "arguments": getattr(item, "arguments", ""),
                                },
                            }
                        )

        # Calculate usage and cost
        usage_data = response.usage
        if usage_data:
            # Responses API usage has different field names
            prompt_tokens = getattr(usage_data, "input_tokens", 0)
            completion_tokens = getattr(usage_data, "output_tokens", 0)
            usage = self._calculate_cost(request.model, prompt_tokens, completion_tokens)
        else:
            usage = Usage()

        # Get finish reason from status
        finish_reason = response.status if hasattr(response, "status") else None

        return CompletionResponse(
            id=response.id,
            model=response.model,
            content=content,
            finish_reason=finish_reason,
            usage=usage,
            tool_calls=tool_calls_list,
            raw_response=response,
            endpoint_used=APIEndpoint.RESPONSES,
        )

    def _responses_api_stream(self, request: CompletionRequest) -> Iterator[CompletionResponse]:
        """Execute streaming request using Responses API"""
        # Convert messages to input format
        input_items = []
        for msg in request.messages:
            input_items.append(
                {
                    "type": "message",
                    "role": msg.get("role", "user"),
                    "content": [{"type": "input_text", "text": msg.get("content", "")}],
                }
            )

        params: Dict[str, Any] = {
            "model": request.model,
            "input": input_items,
            "temperature": request.temperature,
            "top_p": request.top_p,
        }

        if request.max_tokens is not None:
            params["max_output_tokens"] = request.max_tokens
        if not isinstance(request.tools, NotGiven):
            params["tools"] = request.tools
        if not isinstance(request.tool_choice, NotGiven):
            params["tool_choice"] = request.tool_choice
        if not isinstance(request.response_format, NotGiven):
            # Responses API uses response_format for structured outputs
            params["response_format"] = request.response_format

        # Use stream() method for Responses API as context manager
        accumulated_content = ""
        accumulated_tool_calls: list[Dict[str, Any]] = []
        # Track tool calls being built incrementally
        current_tool_calls: Dict[int, Dict[str, Any]] = {}
        last_id = ""
        last_model = request.model
        last_finish_reason = None

        with self.client.responses.stream(**params) as stream:
            for event in stream:
                # Use Any type for event since union is complex
                event_any: Any = event

                # Extract event data based on type
                if hasattr(event_any, "type"):
                    event_type = event_any.type

                    # Handle output text delta events
                    if event_type == "response.output_text.delta":
                        if hasattr(event_any, "delta"):
                            delta_text = str(event_any.delta)
                            accumulated_content += delta_text

                            yield CompletionResponse(
                                id=getattr(event_any, "response_id", last_id),
                                model=last_model,
                                content=delta_text,
                                finish_reason=None,
                                usage=Usage(),
                                tool_calls=[],
                                raw_response=event_any,
                                endpoint_used=APIEndpoint.RESPONSES,
                            )

                    # Handle function call arguments delta
                    elif event_type == "response.function_call_arguments.delta":
                        if hasattr(event_any, "index") and hasattr(event_any, "delta"):
                            idx = event_any.index
                            if idx not in current_tool_calls:
                                current_tool_calls[idx] = {
                                    "id": getattr(event_any, "call_id", f"call_{idx}"),
                                    "type": "function",
                                    "function": {
                                        "name": getattr(event_any, "name", ""),
                                        "arguments": "",
                                    },
                                }
                            # Accumulate arguments incrementally
                            current_tool_calls[idx]["function"]["arguments"] += str(event_any.delta)

                    # Handle function call arguments done
                    elif event_type == "response.function_call_arguments.done":
                        if hasattr(event_any, "index"):
                            idx = event_any.index
                            if idx in current_tool_calls:
                                # Finalize this tool call
                                tool_call = current_tool_calls[idx]
                                # Update with complete information if available
                                if hasattr(event_any, "name"):
                                    tool_call["function"]["name"] = event_any.name
                                if hasattr(event_any, "arguments"):
                                    tool_call["function"]["arguments"] = event_any.arguments
                                accumulated_tool_calls.append(tool_call)

                    # Handle completion event
                    elif event_type == "response.completed":
                        if hasattr(event_any, "response"):
                            response = event_any.response
                            last_id = response.id
                            last_model = response.model
                            last_finish_reason = (
                                response.status if hasattr(response, "status") else None
                            )

        # Final response with complete data
        yield CompletionResponse(
            id=last_id,
            model=last_model,
            content=accumulated_content,
            finish_reason=last_finish_reason,
            usage=Usage(),
            tool_calls=accumulated_tool_calls,
            raw_response=None,
            endpoint_used=APIEndpoint.RESPONSES,
        )

    def _chat_completions_complete(self, request: CompletionRequest) -> CompletionResponse:
        """Execute request using Chat Completions API (fallback)"""
        params: Dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "frequency_penalty": request.frequency_penalty,
            "presence_penalty": request.presence_penalty,
        }

        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens
        if not isinstance(request.stop, NotGiven):
            params["stop"] = request.stop
        if not isinstance(request.tools, NotGiven):
            params["tools"] = request.tools
        if not isinstance(request.tool_choice, NotGiven):
            params["tool_choice"] = request.tool_choice
        if not isinstance(request.response_format, NotGiven):
            params["response_format"] = request.response_format

        response = self.client.chat.completions.create(**params)
        response = cast(ChatCompletion, response)

        # Extract content and tool calls
        content = None
        tool_calls_list: list[Dict[str, Any]] = []

        if response.choices and len(response.choices) > 0:
            choice = response.choices[0]
            message = choice.message
            if message.content:
                content = message.content
            if message.tool_calls:
                for tc in message.tool_calls:
                    # Handle union type for tool calls
                    if hasattr(tc, "function") and tc.function:
                        tool_calls_list.append(
                            {
                                "id": tc.id,
                                "type": tc.type,
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                        )

        # Calculate usage and cost
        usage_data = response.usage
        if usage_data:
            usage = self._calculate_cost(
                request.model,
                usage_data.prompt_tokens,
                usage_data.completion_tokens,
            )
        else:
            usage = Usage()

        return CompletionResponse(
            id=response.id,
            model=response.model,
            content=content,
            finish_reason=response.choices[0].finish_reason if response.choices else None,
            usage=usage,
            tool_calls=tool_calls_list,
            raw_response=response,
            endpoint_used=APIEndpoint.CHAT_COMPLETIONS,
        )

    def _chat_completions_stream(self, request: CompletionRequest) -> Iterator[CompletionResponse]:
        """Execute streaming request using Chat Completions API"""
        params: Dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "frequency_penalty": request.frequency_penalty,
            "presence_penalty": request.presence_penalty,
            "stream": True,
        }

        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens
        if not isinstance(request.stop, NotGiven):
            params["stop"] = request.stop
        if not isinstance(request.tools, NotGiven):
            params["tools"] = request.tools
        if not isinstance(request.tool_choice, NotGiven):
            params["tool_choice"] = request.tool_choice
        if not isinstance(request.response_format, NotGiven):
            params["response_format"] = request.response_format

        stream = self.client.chat.completions.create(**params)

        accumulated_content = ""
        # Track tool calls being built incrementally by index
        current_tool_calls: Dict[int, Dict[str, Any]] = {}
        last_id = ""
        last_model = request.model
        last_finish_reason = None

        for chunk in stream:
            chunk = cast(ChatCompletionChunk, chunk)
            last_id = chunk.id
            last_model = chunk.model

            if chunk.choices and len(chunk.choices) > 0:
                choice = chunk.choices[0]
                delta = choice.delta

                # Accumulate content
                if delta.content:
                    accumulated_content += delta.content

                # Accumulate tool calls by index
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        # Each tool call delta has an index to track which call it belongs to
                        idx = tc.index if hasattr(tc, "index") else 0

                        # Initialize tool call entry if this is the first chunk for this index
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": tc.id if hasattr(tc, "id") else "",
                                "type": tc.type if hasattr(tc, "type") else "function",
                                "function": {
                                    "name": "",
                                    "arguments": "",
                                },
                            }

                        # Update tool call with delta information
                        if hasattr(tc, "id") and tc.id:
                            current_tool_calls[idx]["id"] = tc.id
                        if hasattr(tc, "type") and tc.type:
                            current_tool_calls[idx]["type"] = tc.type

                        # Accumulate function name and arguments incrementally
                        if tc.function:
                            if hasattr(tc.function, "name") and tc.function.name:
                                current_tool_calls[idx]["function"]["name"] = tc.function.name
                            if hasattr(tc.function, "arguments") and tc.function.arguments:
                                current_tool_calls[idx]["function"]["arguments"] += (
                                    tc.function.arguments
                                )

                if choice.finish_reason:
                    last_finish_reason = choice.finish_reason

                yield CompletionResponse(
                    id=chunk.id,
                    model=chunk.model,
                    content=delta.content,
                    finish_reason=choice.finish_reason,
                    usage=Usage(),
                    tool_calls=[],  # Don't emit partial tool calls in each chunk
                    raw_response=chunk,
                    endpoint_used=APIEndpoint.CHAT_COMPLETIONS,
                )

        # Final response with accumulated tool calls
        # Convert tool calls dict to sorted list by index
        final_tool_calls = [current_tool_calls[i] for i in sorted(current_tool_calls.keys())]

        yield CompletionResponse(
            id=last_id,
            model=last_model,
            content=accumulated_content,
            finish_reason=last_finish_reason,
            usage=Usage(),
            tool_calls=final_tool_calls,
            raw_response=None,
            endpoint_used=APIEndpoint.CHAT_COMPLETIONS,
        )

    def complete(
        self, request: CompletionRequest
    ) -> Union[CompletionResponse, Iterator[CompletionResponse]]:
        """
        Execute completion request using configured endpoint.

        Args:
            request: Completion request parameters

        Returns:
            CompletionResponse for non-streaming, Iterator[CompletionResponse] for streaming
        """
        moderator = get_content_moderator()
        moderator.bind_client(self.client)
        self._moderate_request(request, moderator)

        # Select endpoint based on policy
        endpoint = self.config.preferred_endpoint

        if request.stream:
            if endpoint == APIEndpoint.RESPONSES:
                iterator = self._responses_api_stream(request)
            else:
                iterator = self._chat_completions_stream(request)
            return self._wrap_stream_with_moderation(iterator, moderator, model=request.model)
        else:
            if endpoint == APIEndpoint.RESPONSES:
                response = self._responses_api_complete(request)
            else:
                response = self._chat_completions_complete(request)
            return self._apply_output_moderation(response, moderator)


def create_provider(
    api_key: Optional[str] = None,
    preferred_endpoint: APIEndpoint = APIEndpoint.RESPONSES,
    **kwargs: Any,
) -> OpenAIProvider:
    """
    Factory function to create OpenAI provider.

    Args:
        api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        preferred_endpoint: API endpoint to use (RESPONSES or CHAT_COMPLETIONS)
        **kwargs: Additional ProviderConfig parameters

    Returns:
        Configured OpenAIProvider instance
    """
    config = ProviderConfig(api_key=api_key, preferred_endpoint=preferred_endpoint, **kwargs)
    return OpenAIProvider(config)
