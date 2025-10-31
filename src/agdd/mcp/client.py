"""
Async MCP Client with resilience patterns.

Provides a robust client for invoking remote MCP servers with:
- Multiple transport protocols (stdio, websocket, HTTP)
- Exponential backoff with jitter
- Circuit breaker pattern
- Request timeout and cancellation
- Connection pooling
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class TransportType(str, Enum):
    """MCP transport protocol types."""

    STDIO = "stdio"
    WEBSOCKET = "websocket"
    HTTP = "http"


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close from half-open
    timeout_seconds: int = 60  # Time in open state before half-open
    half_open_max_calls: int = 1  # Max concurrent calls in half-open


@dataclass
class RetryConfig:
    """Retry configuration with exponential backoff."""

    max_attempts: int = 3
    base_delay_ms: int = 100
    max_delay_ms: int = 10000
    exponential_base: float = 2.0
    jitter: bool = True


class CircuitBreaker:
    """
    Circuit breaker for fault tolerance.

    Prevents cascading failures by temporarily blocking requests
    to a failing service.
    """

    def __init__(self, config: CircuitBreakerConfig):
        """Initialize circuit breaker."""
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0

    def can_attempt(self) -> bool:
        """Check if a request can be attempted."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if self.last_failure_time:
                elapsed = datetime.utcnow() - self.last_failure_time
                if elapsed.total_seconds() >= self.config.timeout_seconds:
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Allow limited concurrent calls in half-open state
            if self.half_open_calls < self.config.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False

        return False

    def record_success(self) -> None:
        """Record a successful request."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                logger.info("Circuit breaker closing after successful recovery")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed request."""
        self.last_failure_time = datetime.utcnow()

        if self.state == CircuitState.HALF_OPEN:
            logger.warning("Circuit breaker reopening after failure in HALF_OPEN")
            self.state = CircuitState.OPEN
            self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.config.failure_threshold:
                logger.warning(
                    f"Circuit breaker opening after {self.failure_count} failures"
                )
                self.state = CircuitState.OPEN


class MCPClientError(Exception):
    """Base exception for MCP client errors."""

    pass


class MCPTimeoutError(MCPClientError):
    """Request timeout error."""

    pass


class MCPCircuitOpenError(MCPClientError):
    """Circuit breaker is open."""

    pass


class MCPTransportError(MCPClientError):
    """Transport-level error."""

    pass


class AsyncMCPClient:
    """
    Async MCP client with resilience patterns.

    Supports multiple transport protocols and provides built-in
    retry logic, circuit breaker, and timeout handling.
    """

    def __init__(
        self,
        server_name: str,
        transport: TransportType,
        config: Dict[str, Any],
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    ):
        """
        Initialize MCP client.

        Args:
            server_name: MCP server name
            transport: Transport protocol type
            config: Transport-specific configuration
            retry_config: Retry configuration (optional)
            circuit_breaker_config: Circuit breaker configuration (optional)
        """
        self.server_name = server_name
        self.transport = transport
        self.config = config
        self.retry_config = retry_config or RetryConfig()
        self.circuit_breaker = CircuitBreaker(
            circuit_breaker_config or CircuitBreakerConfig()
        )
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the client (establish connections, etc.)."""
        if self._initialized:
            return

        logger.info(f"Initializing MCP client for {self.server_name} ({self.transport})")

        # Transport-specific initialization
        if self.transport == TransportType.STDIO:
            await self._initialize_stdio()
        elif self.transport == TransportType.WEBSOCKET:
            await self._initialize_websocket()
        elif self.transport == TransportType.HTTP:
            await self._initialize_http()

        self._initialized = True

    async def _initialize_stdio(self) -> None:
        """Initialize stdio transport."""
        # Placeholder: Would launch subprocess and set up JSON-RPC over stdio
        logger.debug(f"Initializing stdio transport for {self.server_name}")

    async def _initialize_websocket(self) -> None:
        """Initialize websocket transport."""
        # Placeholder: Would establish WebSocket connection
        logger.debug(f"Initializing websocket transport for {self.server_name}")

    async def _initialize_http(self) -> None:
        """Initialize HTTP transport."""
        # Placeholder: Would set up HTTP client with connection pool
        logger.debug(f"Initializing HTTP transport for {self.server_name}")

    async def close(self) -> None:
        """Close the client and cleanup resources."""
        if not self._initialized:
            return

        logger.info(f"Closing MCP client for {self.server_name}")

        # Transport-specific cleanup
        if self.transport == TransportType.STDIO:
            await self._close_stdio()
        elif self.transport == TransportType.WEBSOCKET:
            await self._close_websocket()
        elif self.transport == TransportType.HTTP:
            await self._close_http()

        self._initialized = False

    async def _close_stdio(self) -> None:
        """Close stdio transport."""
        logger.debug(f"Closing stdio transport for {self.server_name}")

    async def _close_websocket(self) -> None:
        """Close websocket transport."""
        logger.debug(f"Closing websocket transport for {self.server_name}")

    async def _close_http(self) -> None:
        """Close HTTP transport."""
        logger.debug(f"Closing HTTP transport for {self.server_name}")

    async def invoke(
        self,
        tool: str,
        args: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Invoke a tool on the MCP server with retry and circuit breaker.

        Args:
            tool: Tool name to invoke
            args: Tool arguments
            timeout: Request timeout in seconds (default: 30)

        Returns:
            Tool result as dictionary

        Raises:
            MCPClientError: On invocation failure
            MCPTimeoutError: On timeout
            MCPCircuitOpenError: If circuit breaker is open
        """
        if not self._initialized:
            await self.initialize()

        # Check circuit breaker
        if not self.circuit_breaker.can_attempt():
            raise MCPCircuitOpenError(
                f"Circuit breaker is {self.circuit_breaker.state.value} "
                f"for server {self.server_name}"
            )

        timeout = timeout or 30.0
        attempt = 0

        while attempt < self.retry_config.max_attempts:
            attempt += 1

            try:
                # Attempt invocation with timeout
                result = await asyncio.wait_for(
                    self._invoke_internal(tool, args),
                    timeout=timeout,
                )

                # Success - record and return
                self.circuit_breaker.record_success()
                logger.debug(
                    f"Successfully invoked {self.server_name}.{tool} "
                    f"(attempt {attempt}/{self.retry_config.max_attempts})"
                )
                return result

            except asyncio.TimeoutError:
                logger.warning(
                    f"Timeout invoking {self.server_name}.{tool} "
                    f"(attempt {attempt}/{self.retry_config.max_attempts})"
                )
                self.circuit_breaker.record_failure()

                if attempt >= self.retry_config.max_attempts:
                    raise MCPTimeoutError(
                        f"Timeout invoking {self.server_name}.{tool} after {attempt} attempts"
                    )

            except Exception as e:
                logger.warning(
                    f"Error invoking {self.server_name}.{tool}: {e} "
                    f"(attempt {attempt}/{self.retry_config.max_attempts})"
                )
                self.circuit_breaker.record_failure()

                if attempt >= self.retry_config.max_attempts:
                    raise MCPClientError(
                        f"Failed to invoke {self.server_name}.{tool}: {e}"
                    ) from e

            # Calculate backoff delay with exponential backoff and optional jitter
            if attempt < self.retry_config.max_attempts:
                delay = self._calculate_backoff_delay(attempt)
                logger.debug(f"Retrying after {delay:.2f}s...")
                await asyncio.sleep(delay)

        # Should not reach here, but for type safety
        raise MCPClientError(f"Failed to invoke {self.server_name}.{tool} after retries")

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay with jitter.

        Args:
            attempt: Current attempt number (1-based)

        Returns:
            Delay in seconds
        """
        # Exponential backoff: delay = base * exponential_base^(attempt - 1)
        delay_ms = self.retry_config.base_delay_ms * (
            self.retry_config.exponential_base ** (attempt - 1)
        )

        # Cap at max delay
        delay_ms = min(delay_ms, self.retry_config.max_delay_ms)

        # Add jitter: randomize ±25% to avoid thundering herd
        if self.retry_config.jitter:
            jitter_range = delay_ms * 0.25
            delay_ms += random.uniform(-jitter_range, jitter_range)

        return delay_ms / 1000.0  # Convert to seconds

    async def _invoke_internal(
        self,
        tool: str,
        args: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Internal invocation method (transport-specific).

        Args:
            tool: Tool name
            args: Tool arguments

        Returns:
            Tool result

        Raises:
            MCPTransportError: On transport-level errors
        """
        if self.transport == TransportType.STDIO:
            return await self._invoke_stdio(tool, args)
        elif self.transport == TransportType.WEBSOCKET:
            return await self._invoke_websocket(tool, args)
        elif self.transport == TransportType.HTTP:
            return await self._invoke_http(tool, args)
        else:
            raise MCPTransportError(f"Unsupported transport: {self.transport}")

    async def _invoke_stdio(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke via stdio transport."""
        # Placeholder: Would send JSON-RPC request over stdin/stdout
        logger.debug(f"Invoking {tool} via stdio")

        # Simulate processing
        await asyncio.sleep(0.1)

        # Placeholder result
        return {
            "success": True,
            "result": {"tool": tool, "args": args},
        }

    async def _invoke_websocket(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke via websocket transport."""
        # Placeholder: Would send JSON-RPC over WebSocket
        logger.debug(f"Invoking {tool} via websocket")

        # Simulate processing
        await asyncio.sleep(0.1)

        return {
            "success": True,
            "result": {"tool": tool, "args": args},
        }

    async def _invoke_http(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke via HTTP transport."""
        # Placeholder: Would send HTTP POST request
        logger.debug(f"Invoking {tool} via HTTP")

        # Simulate processing
        await asyncio.sleep(0.1)

        return {
            "success": True,
            "result": {"tool": tool, "args": args},
        }

    def get_circuit_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        return self.circuit_breaker.state

    def reset_circuit(self) -> None:
        """Manually reset circuit breaker to closed state."""
        logger.info(f"Manually resetting circuit breaker for {self.server_name}")
        self.circuit_breaker.state = CircuitState.CLOSED
        self.circuit_breaker.failure_count = 0
        self.circuit_breaker.success_count = 0
