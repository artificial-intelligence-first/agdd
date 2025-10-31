"""Unit tests for MCP client."""

from __future__ import annotations

import asyncio

import pytest

from agdd.mcp.client import (
    AsyncMCPClient,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    MCPCircuitOpenError,
    MCPTimeoutError,
    RetryConfig,
    TransportType,
)


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_initial_state_closed(self) -> None:
        """Test circuit breaker starts in CLOSED state."""
        cb = CircuitBreaker(CircuitBreakerConfig())
        assert cb.state == CircuitState.CLOSED
        assert cb.can_attempt()

    def test_opens_after_threshold_failures(self) -> None:
        """Test circuit breaker opens after reaching failure threshold."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker(config)

        # Record failures
        for _ in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert not cb.can_attempt()

    def test_half_open_after_timeout(self) -> None:
        """Test circuit breaker transitions to HALF_OPEN after timeout."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            timeout_seconds=0,  # Immediate transition for testing
        )
        cb = CircuitBreaker(config)

        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Should transition to HALF_OPEN immediately (timeout=0)
        assert cb.can_attempt()
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_after_successes_in_half_open(self) -> None:
        """Test circuit breaker closes after successes in HALF_OPEN."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            timeout_seconds=0,
        )
        cb = CircuitBreaker(config)

        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Transition to HALF_OPEN
        cb.can_attempt()
        assert cb.state == CircuitState.HALF_OPEN

        # Record successes
        cb.record_success()
        cb.record_success()

        assert cb.state == CircuitState.CLOSED

    def test_reopens_on_failure_in_half_open(self) -> None:
        """Test circuit breaker reopens on failure in HALF_OPEN."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            timeout_seconds=0,
        )
        cb = CircuitBreaker(config)

        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Transition to HALF_OPEN
        cb.can_attempt()
        assert cb.state == CircuitState.HALF_OPEN

        # Failure in HALF_OPEN reopens
        cb.record_failure()
        assert cb.state == CircuitState.OPEN


class TestRetryLogic:
    """Test retry and backoff logic."""

    async def test_backoff_calculation(self) -> None:
        """Test exponential backoff calculation."""
        config = RetryConfig(
            base_delay_ms=100,
            exponential_base=2.0,
            jitter=False,
        )

        client = AsyncMCPClient(
            server_name="test-server",
            transport=TransportType.HTTP,
            config={},
            retry_config=config,
        )

        # Test backoff delays
        delay1 = client._calculate_backoff_delay(1)
        delay2 = client._calculate_backoff_delay(2)
        delay3 = client._calculate_backoff_delay(3)

        # Without jitter: delay = base * exponential_base^(attempt - 1)
        assert abs(delay1 - 0.1) < 0.01  # 100ms * 2^0 = 100ms
        assert abs(delay2 - 0.2) < 0.01  # 100ms * 2^1 = 200ms
        assert abs(delay3 - 0.4) < 0.01  # 100ms * 2^2 = 400ms

    async def test_backoff_with_jitter(self) -> None:
        """Test that jitter adds randomness to backoff."""
        config = RetryConfig(
            base_delay_ms=100,
            exponential_base=2.0,
            jitter=True,
        )

        client = AsyncMCPClient(
            server_name="test-server",
            transport=TransportType.HTTP,
            config={},
            retry_config=config,
        )

        # With jitter, delays should vary but be in expected range
        delays = [client._calculate_backoff_delay(1) for _ in range(10)]

        # All delays should be near 0.1s but with variance
        for delay in delays:
            assert 0.075 <= delay <= 0.125  # ±25% jitter


class TestMCPClient:
    """Test AsyncMCPClient functionality."""

    async def test_client_initialization(self) -> None:
        """Test client initialization."""
        client = AsyncMCPClient(
            server_name="test-server",
            transport=TransportType.HTTP,
            config={"url": "http://localhost:8080"},
        )

        assert client.server_name == "test-server"
        assert client.transport == TransportType.HTTP
        assert not client._initialized

        await client.initialize()
        assert client._initialized

        await client.close()
        assert not client._initialized

    async def test_invoke_success(self) -> None:
        """Test successful tool invocation."""
        client = AsyncMCPClient(
            server_name="test-server",
            transport=TransportType.HTTP,
            config={},
        )

        result = await client.invoke(
            tool="test_tool",
            args={"arg1": "value1"},
            timeout=5.0,
        )

        assert result["success"]
        assert result["result"]["tool"] == "test_tool"
        assert result["result"]["args"]["arg1"] == "value1"

        await client.close()

    async def test_invoke_with_circuit_open(self) -> None:
        """Test invocation fails when circuit is open."""
        config = CircuitBreakerConfig(failure_threshold=1)

        client = AsyncMCPClient(
            server_name="test-server",
            transport=TransportType.HTTP,
            config={},
            circuit_breaker_config=config,
        )

        # Force circuit open
        client.circuit_breaker.record_failure()
        assert client.circuit_breaker.state == CircuitState.OPEN

        # Invocation should fail immediately
        with pytest.raises(MCPCircuitOpenError):
            await client.invoke("test_tool", {})

        await client.close()

    async def test_circuit_state_tracking(self) -> None:
        """Test circuit state can be queried."""
        client = AsyncMCPClient(
            server_name="test-server",
            transport=TransportType.HTTP,
            config={},
        )

        assert client.get_circuit_state() == CircuitState.CLOSED

        # Open circuit
        client.circuit_breaker.record_failure()
        client.circuit_breaker.record_failure()
        client.circuit_breaker.record_failure()
        client.circuit_breaker.record_failure()
        client.circuit_breaker.record_failure()

        assert client.get_circuit_state() == CircuitState.OPEN

        # Reset circuit
        client.reset_circuit()
        assert client.get_circuit_state() == CircuitState.CLOSED

        await client.close()

    async def test_multiple_transports(self) -> None:
        """Test client supports multiple transport types."""
        for transport in [TransportType.STDIO, TransportType.WEBSOCKET, TransportType.HTTP]:
            client = AsyncMCPClient(
                server_name="test-server",
                transport=transport,
                config={},
            )

            await client.initialize()
            assert client._initialized

            result = await client.invoke("test_tool", {})
            assert result["success"]

            await client.close()


class TestMCPDecorators:
    """Test MCP decorators."""

    async def test_resolve_secret_env(self) -> None:
        """Test resolving secrets from environment."""
        import os

        from agdd.mcp.decorators import resolve_secret

        # Set test environment variable
        os.environ["TEST_SECRET"] = "secret_value"

        resolved = resolve_secret("env://TEST_SECRET")
        assert resolved == "secret_value"

        # Plain value
        plain = resolve_secret("plain_value")
        assert plain == "plain_value"

        # Clean up
        del os.environ["TEST_SECRET"]

    async def test_resolve_secret_missing_env(self) -> None:
        """Test error when environment variable is missing."""
        from agdd.mcp.decorators import resolve_secret

        with pytest.raises(ValueError, match="not found"):
            resolve_secret("env://NONEXISTENT_VAR")

    async def test_get_auth_config(self) -> None:
        """Test authentication config resolution."""
        import os

        from agdd.mcp.decorators import get_auth_config

        # Set test environment variables
        os.environ["API_KEY"] = "test_key"
        os.environ["API_SECRET"] = "test_secret"

        auth_config = get_auth_config({
            "api_key": "env://API_KEY",
            "api_secret": "env://API_SECRET",
            "plain_value": "plain",
        })

        assert auth_config["api_key"] == "test_key"
        assert auth_config["api_secret"] == "test_secret"
        assert auth_config["plain_value"] == "plain"

        # Clean up
        del os.environ["API_KEY"]
        del os.environ["API_SECRET"]

    async def test_mcp_tool_decorator(self) -> None:
        """Test @mcp_tool decorator."""
        import os

        from agdd.mcp.decorators import mcp_tool

        os.environ["GITHUB_TOKEN"] = "test_token"

        @mcp_tool(
            server="github",
            tool="create_issue",
            auth={"token": "env://GITHUB_TOKEN"},
            timeout=30.0,
        )
        async def create_issue(repo: str, title: str) -> dict[str, Any]:
            pass

        result = await create_issue("test/repo", "Test Issue")

        assert result["server"] == "github"
        assert result["tool"] == "create_issue"
        assert "GITHUB_TOKEN" not in result  # Should not expose token
        assert result["auth_keys"] == ["token"]

        # Clean up
        del os.environ["GITHUB_TOKEN"]

    async def test_mcp_cached_decorator(self) -> None:
        """Test @mcp_cached decorator."""
        from agdd.mcp.decorators import mcp_cached

        call_count = 0

        @mcp_cached(ttl_seconds=1)
        async def expensive_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call
        result1 = await expensive_function(5)
        assert result1 == 10
        assert call_count == 1

        # Second call (cached)
        result2 = await expensive_function(5)
        assert result2 == 10
        assert call_count == 1  # Should not increment

        # Wait for cache expiration
        await asyncio.sleep(1.1)

        # Third call (cache expired)
        result3 = await expensive_function(5)
        assert result3 == 10
        assert call_count == 2  # Should increment
