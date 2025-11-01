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
import json
import logging
import random
import uuid
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, Optional

import httpx
import websockets

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
                elapsed = datetime.now(UTC) - self.last_failure_time
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
        self.last_failure_time = datetime.now(UTC)

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
        self._init_lock = asyncio.Lock()
        self._stdio_process: Optional[asyncio.subprocess.Process] = None
        self._stdio_lock = asyncio.Lock()
        self._http_client: Optional[httpx.AsyncClient] = None
        self._http_base_url: Optional[str] = None
        self._http_headers: Dict[str, str] = {}
        self._ws_uri: Optional[str] = None
        self._ws_headers: Dict[str, str] = {}
        self._ws_connection: Optional[Any] = None
        self._ws_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the client (establish connections, etc.)."""
        if self._initialized:
            return

        async with self._init_lock:
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
        """Initialize stdio transport by starting the configured process."""
        if self._stdio_process and self._stdio_process.returncode is None:
            return

        command = self.config.get("command")
        args = self.config.get("args", [])
        env_vars = self.config.get("env") or {}

        if not command:
            raise MCPTransportError("STDIO transport requires 'command' in config")

        env = os.environ.copy()
        env.update(env_vars)

        logger.debug(
            "Launching STDIO MCP server %s with command %s %s",
            self.server_name,
            command,
            " ".join(str(arg) for arg in args),
        )

        self._stdio_process = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._stdio_lock = asyncio.Lock()

    async def _initialize_websocket(self) -> None:
        """Initialize websocket transport."""
        if self._ws_uri:
            return

        uri = self.config.get("url")
        if not uri:
            raise MCPTransportError("WebSocket transport requires 'url' in config")

        self._ws_uri = uri
        self._ws_headers = self.config.get("headers", {})
        self._ws_lock = asyncio.Lock()
        logger.debug("Configured websocket transport for %s -> %s", self.server_name, uri)

    async def _initialize_http(self) -> None:
        """Initialize HTTP transport."""
        if self._http_client is not None:
            return

        base_url = self.config.get("url")
        if not base_url:
            raise MCPTransportError("HTTP transport requires 'url' in config")

        headers = self.config.get("headers", {})
        timeout = self.config.get("timeout")
        if timeout is None:
            limits = self.config.get("limits") or {}
            timeout = limits.get("timeout_s")

        logger.debug(
            "Initializing HTTP transport for %s with base URL %s",
            self.server_name,
            base_url,
        )

        self._http_base_url = base_url
        self._http_headers = headers
        self._http_client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers=headers,
        )

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
        if self._stdio_process is None:
            return

        logger.debug(f"Closing stdio transport for {self.server_name}")

        try:
            if self._stdio_process.returncode is None:
                self._stdio_process.terminate()
                try:
                    await asyncio.wait_for(self._stdio_process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    logger.warning(
                        "STDIO process for %s did not terminate, killing",
                        self.server_name,
                    )
                    self._stdio_process.kill()
                    await self._stdio_process.wait()
        finally:
            self._stdio_process = None

    async def _close_websocket(self) -> None:
        """Close websocket transport."""
        if self._ws_connection is None:
            return

        logger.debug(f"Closing websocket transport for {self.server_name}")

        try:
            await self._ws_connection.close()
        finally:
            self._ws_connection = None

    async def _close_http(self) -> None:
        """Close HTTP transport."""
        if self._http_client is None:
            return

        logger.debug(f"Closing HTTP transport for {self.server_name}")
        await self._http_client.aclose()
        self._http_client = None

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

    def _build_request(self, tool: str, args: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        """Create a JSON-RPC request payload."""
        request_id = uuid.uuid4().hex
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": tool,
            "params": args,
        }
        return request_id, request

    def _parse_response(self, request_id: str, response: Dict[str, Any]) -> Dict[str, Any]:
        """Validate JSON-RPC response and extract result."""
        if "error" in response:
            error = response["error"]
            message = error.get("message", "Unknown MCP error")
            raise MCPClientError(f"MCP error: {message}")

        if response.get("id") != request_id:
            raise MCPClientError("Mismatched response ID in MCP response")

        result = response.get("result")
        if result is None:
            return {}
        if isinstance(result, dict):
            return result
        return {"value": result}

    async def _invoke_stdio(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke via stdio transport."""
        if (
            self._stdio_process is None
            or self._stdio_process.stdin is None
            or self._stdio_process.stdout is None
        ):
            raise MCPTransportError("STDIO process not initialized")

        if self._stdio_process.returncode is not None:
            raise MCPTransportError("STDIO process is not running")

        request_id, request = self._build_request(tool, args)
        payload = json.dumps(request, ensure_ascii=False) + "\n"

        async with self._stdio_lock:
            logger.debug("Sending STDIO MCP request %s: %s", request_id, request)
            self._stdio_process.stdin.write(payload.encode("utf-8"))
            await self._stdio_process.stdin.drain()

            raw_response = await self._stdio_process.stdout.readline()
            if not raw_response:
                raise MCPTransportError("STDIO transport closed unexpectedly")

            try:
                response_data = json.loads(raw_response.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise MCPTransportError("Invalid JSON from STDIO transport") from exc

        logger.debug("Received STDIO MCP response %s: %s", request_id, response_data)
        return self._parse_response(request_id, response_data)

    async def _invoke_websocket(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke via websocket transport."""
        if not self._ws_uri:
            raise MCPTransportError("WebSocket transport not initialized")

        request_id, request = self._build_request(tool, args)

        async with self._ws_lock:
            try:
                if self._ws_connection is None or self._ws_connection.closed:
                    logger.debug(
                        "Opening websocket connection for %s to %s",
                        self.server_name,
                        self._ws_uri,
                    )
                    self._ws_connection = await websockets.connect(
                        self._ws_uri,
                        extra_headers=self._ws_headers or None,
                    )

                await self._ws_connection.send(json.dumps(request, ensure_ascii=False))
                raw_response = await self._ws_connection.recv()
            except websockets.ConnectionClosed as exc:
                logger.warning("WebSocket connection closed for %s: %s", self.server_name, exc)
                self._ws_connection = None
                raise MCPTransportError("WebSocket connection closed") from exc

        try:
            response_data = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise MCPTransportError("Invalid JSON from WebSocket transport") from exc

        logger.debug("Received WebSocket MCP response %s: %s", request_id, response_data)
        return self._parse_response(request_id, response_data)

    async def _invoke_http(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke via HTTP transport."""
        if self._http_client is None or self._http_base_url is None:
            raise MCPTransportError("HTTP client is not initialized")

        request_id, request = self._build_request(tool, args)

        try:
            response = await self._http_client.post(
                self._http_base_url,
                json=request,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MCPTransportError(f"HTTP request failed: {exc}") from exc

        try:
            response_data = response.json()
        except ValueError as exc:
            raise MCPTransportError("Invalid JSON from HTTP transport") from exc

        logger.debug("Received HTTP MCP response %s: %s", request_id, response_data)
        return self._parse_response(request_id, response_data)

    def get_circuit_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        return self.circuit_breaker.state

    def reset_circuit(self) -> None:
        """Manually reset circuit breaker to closed state."""
        logger.info(f"Manually resetting circuit breaker for {self.server_name}")
        self.circuit_breaker.state = CircuitState.CLOSED
        self.circuit_breaker.failure_count = 0
        self.circuit_breaker.success_count = 0
