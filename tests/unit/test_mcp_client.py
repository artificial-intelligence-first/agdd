"""Unit tests for AsyncMCPClient."""

from __future__ import annotations

import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
import warnings

from magsag.mcp.client import (
    AsyncMCPClient,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    MCPCircuitOpenError,
    MCPClientError,
    MCPTimeoutError,
    RetryConfig,
    TransportType,
)


warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module=r"websockets.*",
)


class TestCircuitBreaker:
    """Tests for circuit breaker state transitions."""

    def test_initial_state_closed(self) -> None:
        cb = CircuitBreaker(CircuitBreakerConfig())
        assert cb.state == CircuitState.CLOSED
        assert cb.can_attempt()

    def test_opens_after_threshold_failures(self) -> None:
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker(config)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.can_attempt()

    def test_half_open_after_timeout(self) -> None:
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0)
        cb = CircuitBreaker(config)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_attempt()
        state_after_attempt: CircuitState = cb.state
        assert state_after_attempt == CircuitState.HALF_OPEN

    def test_closes_after_successes(self) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=2,
            timeout_seconds=0,
        )
        cb = CircuitBreaker(config)
        cb.record_failure()
        cb.can_attempt()  # transition to HALF_OPEN
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reopens_on_failure_in_half_open(self) -> None:
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0)
        cb = CircuitBreaker(config)
        cb.record_failure()
        cb.can_attempt()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
class TestMCPClient:
    """Tests for AsyncMCPClient behaviour."""

    async def test_invoke_success(self) -> None:
        client = AsyncMCPClient(
            server_name="test",
            transport=TransportType.HTTP,
            config={"url": "https://example.com"},
        )
        cast(Any, client)._invoke_internal = AsyncMock(return_value={"ok": True})

        result = await client.invoke(tool="ping", args={})
        assert result == {"ok": True}
        await client.close()

    async def test_invoke_retries_then_succeeds(self) -> None:
        client = AsyncMCPClient(
            server_name="test",
            transport=TransportType.HTTP,
            config={"url": "https://example.com"},
            retry_config=RetryConfig(max_attempts=3, jitter=False, base_delay_ms=1),
        )
        side_effects = [RuntimeError("boom"), {"value": 42}]
        cast(Any, client)._invoke_internal = AsyncMock(side_effect=side_effects)

        result = await client.invoke("tool", {})
        assert result == {"value": 42}
        assert client.circuit_breaker.failure_count == 0
        await client.close()

    async def test_invoke_timeout(self) -> None:
        client = AsyncMCPClient(
            server_name="test",
            transport=TransportType.HTTP,
            config={"url": "https://example.com"},
            retry_config=RetryConfig(max_attempts=2, jitter=False),
        )
        cast(Any, client)._invoke_internal = AsyncMock(side_effect=asyncio.TimeoutError())

        with pytest.raises(MCPTimeoutError):
            await client.invoke("tool", {}, timeout=0.01)
        await client.close()

    async def test_invoke_propagates_final_exception(self) -> None:
        client = AsyncMCPClient(
            server_name="test",
            transport=TransportType.HTTP,
            config={"url": "https://example.com"},
            retry_config=RetryConfig(max_attempts=2, jitter=False),
        )
        cast(Any, client)._invoke_internal = AsyncMock(side_effect=ValueError("bad"))

        with pytest.raises(MCPClientError):
            await client.invoke("tool", {})
        await client.close()

    async def test_circuit_open_blocks_invocation(self) -> None:
        client = AsyncMCPClient(
            server_name="test",
            transport=TransportType.HTTP,
            config={"url": "https://example.com"},
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
        )
        client.circuit_breaker.record_failure()
        with pytest.raises(MCPCircuitOpenError):
            await client.invoke("tool", {})
        await client.close()

    async def test_build_and_parse_jsonrpc(self) -> None:
        client = AsyncMCPClient(
            server_name="test",
            transport=TransportType.HTTP,
            config={"url": "https://example.com"},
        )
        request_id, payload = client._build_request("do", {"a": 1})
        assert payload == {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "do",
            "params": {"a": 1},
        }
        parsed = client._parse_response(request_id, {"jsonrpc": "2.0", "id": request_id, "result": {"ok": True}})
        assert parsed == {"ok": True}

        with pytest.raises(MCPClientError):
            client._parse_response(request_id, {"jsonrpc": "2.0", "id": request_id, "error": {"message": "fail"}})
        with pytest.raises(MCPClientError):
            client._parse_response("other", {"jsonrpc": "2.0", "id": request_id, "result": {}})

    async def test_invoke_internal_dispatch(self) -> None:
        scenarios = [
            (TransportType.STDIO, "_invoke_stdio"),
            (TransportType.WEBSOCKET, "_invoke_websocket"),
            (TransportType.HTTP, "_invoke_http"),
        ]
        for transport, method_name in scenarios:
            client = AsyncMCPClient(
                server_name="test",
                transport=transport,
                config={"url": "https://example.com"} if transport != TransportType.STDIO else {"command": "echo"},
            )
            mock = AsyncMock(return_value={"transport": transport.value})
            setattr(client, method_name, mock)
            result = await client._invoke_internal("foo", {})
            assert result == {"transport": transport.value}
            mock.assert_awaited_once()
            await client.close()

    async def test_invoke_http_sends_jsonrpc(self) -> None:
        client = AsyncMCPClient(
            server_name="test",
            transport=TransportType.HTTP,
            config={"url": "https://api.example.com"},
        )
        await client.initialize()

        captured: dict[str, Any] = {}

        class DummyResponse:
            def __init__(self, payload: dict[str, Any]):
                self._payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return self._payload

        async def fake_post(
            url: str,
            *,
            json: dict[str, Any],
            **_: Any,
        ) -> DummyResponse:
            captured["url"] = url
            captured["json"] = json
            return DummyResponse({"jsonrpc": "2.0", "id": json["id"], "result": {"ok": True}})

        http_client = client._http_client
        assert http_client is not None
        post_mock = AsyncMock(side_effect=fake_post)
        setattr(cast(Any, http_client), "post", post_mock)
        result = await client._invoke_http("ping", {"x": 1})
        assert result == {"ok": True}
        assert captured["url"] == "https://api.example.com"
        assert captured["json"]["method"] == "ping"
        await client.close()
