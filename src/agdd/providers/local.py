"""Local LLM provider with Responses API preference and safe chat fallback."""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from agdd.providers.base import LLMResponse
from agdd.providers.openai_compat import OpenAICompatProvider, OpenAICompatProviderConfig

logger = logging.getLogger(__name__)


class ResponsesNotSupportedError(RuntimeError):
    """Raised when the local endpoint does not support the Responses API."""


@dataclass(slots=True)
class LocalProviderConfig:
    """Configuration for the local LLM provider."""

    base_url: str = "http://localhost:8000/v1/"
    api_key: Optional[str] = None
    timeout: float = 60.0
    prefer_responses: bool = True
    fallback_on_error: bool = True
    pricing: dict[str, dict[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.base_url.endswith("/"):
            self.base_url += "/"


class LocalLLMProvider:
    """Local LLM provider with automatic Responses → Chat Completions fallback."""

    _RESPONSES_UNSUPPORTED_STATUS = {400, 404, 405, 501}

    def __init__(
        self,
        config: Optional[LocalProviderConfig] = None,
        *,
        compat_provider: Optional[OpenAICompatProvider] = None,
    ):
        self.config = config or LocalProviderConfig()
        self._client = httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            headers=self._build_headers(),
        )
        if compat_provider is not None:
            self._compat_provider = compat_provider
        else:
            compat_config = OpenAICompatProviderConfig(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                api_key=self.config.api_key,
                pricing=self.config.pricing,
            )
            self._compat_provider = OpenAICompatProvider(config=compat_config)
        self._responses_supported: Optional[bool] = None

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def close(self) -> None:
        """Release network resources."""
        self._client.close()
        compat_close = getattr(self._compat_provider, "close", None)
        if compat_close is None:
            return
        if inspect.iscoroutinefunction(compat_close):
            async def _close_async() -> None:
                await compat_close()

            try:
                asyncio.run(_close_async())
            except RuntimeError as exc:
                if "asyncio.run() cannot be called" not in str(exc):
                    raise
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(_close_async())
                finally:
                    loop.close()
        else:
            compat_close()

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass

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
        """Generate a completion using local LLM with safe fallback."""
        requires_responses = any(
            [
                tools,
                tool_choice,
                response_format,
                reasoning,
                mcp_tools,
            ]
        )

        use_responses = self.config.prefer_responses or requires_responses
        warnings: list[str] = []

        if use_responses and self._responses_supported is not False:
            try:
                response = self._invoke_responses(
                    prompt=prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    tools=tools,
                    tool_choice=tool_choice,
                    response_format=response_format,
                    reasoning=reasoning,
                    mcp_tools=mcp_tools,
                    extra_params=kwargs,
                )
                self._responses_supported = True
                return response
            except ResponsesNotSupportedError as exc:
                self._responses_supported = False
                warnings.append(str(exc))
                logger.warning(str(exc))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in self._RESPONSES_UNSUPPORTED_STATUS:
                    msg = (
                        "Local Responses API endpoint is unavailable "
                        f"(status={exc.response.status_code}). Falling back to chat completions."
                    )
                    self._responses_supported = False
                    warnings.append(msg)
                    logger.warning(msg)
                else:
                    raise
            except httpx.RequestError as exc:
                if not self.config.fallback_on_error:
                    raise
                msg = (
                    "Network error while calling local Responses API "
                    f"({exc}). Falling back to chat completions."
                )
                warnings.append(msg)
                logger.warning(msg)

        if requires_responses:
            warning_msg = (
                "Structured outputs or tool calls were requested but the local endpoint "
                "does not support the Responses API. Downgrading to chat completions."
            )
            warnings.append(warning_msg)
            logger.warning(warning_msg)

        llm_response = self._compat_provider.generate(
            prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            reasoning=reasoning,
            mcp_tools=mcp_tools,
            **kwargs,
        )

        llm_response.metadata.setdefault("endpoint", "chat_completions")
        llm_response.metadata["provider"] = "local"
        llm_response.metadata["fallback"] = "chat_completions"
        if warnings:
            existing_warnings = llm_response.metadata.get("warnings", [])
            if not isinstance(existing_warnings, list):
                existing_warnings = [existing_warnings]
            existing_warnings.extend(warnings)
            llm_response.metadata["warnings"] = existing_warnings

        return llm_response

    def get_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estimate cost using provider pricing (defaults to zero)."""
        pricing = self.config.pricing.get(model)
        if not pricing:
            return 0.0
        prompt_rate = pricing.get("prompt", 0.0)
        completion_rate = pricing.get("completion", 0.0)
        return (input_tokens / 1_000_000) * prompt_rate + (output_tokens / 1_000_000) * completion_rate

    def _invoke_responses(
        self,
        *,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        tools: Optional[list[dict[str, Any]]],
        tool_choice: Optional[str | dict[str, Any]],
        response_format: Optional[dict[str, Any]],
        reasoning: Optional[dict[str, Any]],
        mcp_tools: Optional[list[dict[str, Any]]],
        extra_params: dict[str, Any],
    ) -> LLMResponse:
        """Attempt to call the Responses API on the local endpoint."""
        payload: dict[str, Any] = {
            "model": model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
            "temperature": temperature,
        }

        if max_tokens is not None:
            payload["max_output_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        if response_format:
            payload["response_format"] = response_format
        if reasoning:
            payload["reasoning"] = reasoning
        if mcp_tools:
            payload.setdefault("metadata", {})["mcp_tools"] = mcp_tools
        if extra_params:
            payload.setdefault("metadata", {}).update({"extra_kwargs": extra_params})

        response = self._client.post("responses", json=payload)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and data.get("error"):
            raise ResponsesNotSupportedError(
                f"Local endpoint rejected Responses API request: {data['error']}"
            )

        return self._parse_responses_result(model=model, data=data)

    def _parse_responses_result(self, *, model: str, data: dict[str, Any]) -> LLMResponse:
        """Convert a raw Responses API payload into LLMResponse."""
        output_blocks = data.get("output", [])
        content_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for block in output_blocks:
            block_type = block.get("type")
            if block_type == "message":
                for item in block.get("content", []):
                    item_type = item.get("type")
                    if item_type in {"output_text", "text"}:
                        content_parts.append(item.get("text", ""))
                    elif item_type == "input_text":
                        # Some implementations echo user input
                        continue
            elif block_type in {"function_call", "tool_call"}:
                tool_calls.append(
                    {
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": block.get("name") or block.get("function", {}).get("name", ""),
                            "arguments": block.get("arguments")
                            or block.get("function", {}).get("arguments", ""),
                        },
                    }
                )

        content = "".join(content_parts) if content_parts else data.get("output_text", "")
        usage = data.get("usage") or {}
        input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
        output_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
        cost_usd = self.get_cost(model, input_tokens, output_tokens)

        metadata = {
            "id": data.get("id"),
            "status": data.get("status"),
            "endpoint": "responses",
            "provider": "local",
            "cost_usd": cost_usd,
        }
        if data.get("warnings"):
            metadata["warnings"] = data["warnings"]

        response_format_ok = True
        if data.get("response", {}).get("status") == "failed":
            response_format_ok = False

        return LLMResponse(
            content=content or "",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_calls=tool_calls or None,
            response_format_ok=response_format_ok,
            raw_output_blocks=output_blocks if output_blocks else None,
            metadata=metadata,
        )
