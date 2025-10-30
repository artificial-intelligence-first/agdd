"""MCP Server connection management.

This module handles connections to individual MCP servers,
including lifecycle management and tool execution.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
from asyncio.subprocess import PIPE, Process
from typing import Any, cast

from agdd.mcp.config import MCPServerConfig
from agdd.mcp.tool import MCPTool, MCPToolResult, MCPToolSchema

logger = logging.getLogger(__name__)

# Optional import for PostgreSQL support
try:
    import asyncpg

    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False
    asyncpg = None


class MCPServerError(Exception):
    """Base exception for MCP server errors."""

    pass


class MCPServer:
    """Manages connection to a single MCP server.

    This class handles the lifecycle of an MCP server connection,
    including starting/stopping processes, discovering tools, and
    executing tool calls.
    """

    def __init__(self, config: MCPServerConfig) -> None:
        """Initialize MCP server with configuration.

        Args:
            config: Server configuration loaded from YAML
        """
        self.config = config
        self._process: Process | None = None
        self._stdin: asyncio.StreamWriter | None = None
        self._stdout: asyncio.StreamReader | None = None
        self._stderr: asyncio.StreamReader | None = None
        self._tools: dict[str, MCPTool] = {}
        self._pg_pool: Any = None  # asyncpg.Pool[Any] | None (if asyncpg is installed)
        self._started: bool = False
        self._rpc_counter: int = 0
        self._io_lock = asyncio.Lock()
        self._stderr_task: asyncio.Task[None] | None = None

    @property
    def server_id(self) -> str:
        """Get the server ID."""
        return self.config.server_id

    @property
    def is_started(self) -> bool:
        """Check if the server is started."""
        return self._started

    async def start(self) -> None:
        """Start the MCP server and discover available tools.

        Raises:
            MCPServerError: If server fails to start
        """
        if self._started:
            return

        if self.config.type == "mcp":
            await self._start_mcp_server()
        elif self.config.type == "postgres":
            await self._start_postgres_connection()
        else:
            raise MCPServerError(f"Unknown server type: {self.config.type}")

        self._started = True

    async def stop(self) -> None:
        """Stop the MCP server and clean up resources."""
        if not self._started:
            return

        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            self._process = None
            self._stdin = None
            self._stdout = None
            self._stderr = None

        if self._stderr_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._stderr_task
            self._stderr_task = None

        if self._pg_pool:
            await self._pg_pool.close()
            self._pg_pool = None

        self._started = False
        self._tools.clear()

    async def _start_mcp_server(self) -> None:
        """Start an MCP stdio server process.

        Raises:
            MCPServerError: If server command is not configured
        """
        if not self.config.command:
            raise MCPServerError(f"No command specified for MCP server {self.server_id}")

        # Note: In a production implementation, we would:
        # 1. Start the subprocess with stdin/stdout pipes
        # 2. Implement the MCP protocol handshake
        # 3. Discover available tools via the protocol
        #
        # For now, we create a placeholder implementation that
        # can be extended with the actual MCP protocol later.

        # Placeholder: mark as started without actual process
        # Real implementation would start subprocess and perform handshake
        cmd = [self.config.command, *self.config.args]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=PIPE,
                stdout=PIPE,
                stderr=PIPE,
            )
        except Exception as exc:  # noqa: BLE001
            raise MCPServerError(f"Failed to start MCP server '{self.server_id}': {exc}") from exc

        self._process = process
        self._stdin = process.stdin
        self._stdout = process.stdout
        self._stderr = process.stderr
        self._rpc_counter = 0

        # Drain stderr in the background for debugging purposes
        if self._stderr:
            self._stderr_task = asyncio.create_task(self._drain_stderr())

        try:
            initialize_response = await self._send_request(
                "initialize",
                {
                    "clientInfo": {"name": "agdd", "version": "1.0"},
                    "capabilities": {},
                },
            )
            if "error" in initialize_response:
                raise MCPServerError(f"Initialize failed: {initialize_response['error']}")

            # Notify server that initialization completed
            await self._send_notification("notifications/initialized", {})

            tools_response = await self._send_request("tools/list", {})
            if "error" in tools_response:
                raise MCPServerError(f"tools/list failed: {tools_response['error']}")

            tools_payload = tools_response.get("result", {}).get("tools", [])
            self._register_tools_from_payload(tools_payload)

        except Exception:  # noqa: BLE001
            await self._cleanup_process()
            raise

    async def _start_postgres_connection(self) -> None:
        """Start PostgreSQL connection pool.

        Raises:
            MCPServerError: If connection configuration is missing or invalid
        """
        if not HAS_ASYNCPG:
            raise MCPServerError(
                f"PostgreSQL server '{self.server_id}' requires asyncpg package. "
                "Install it with: pip install asyncpg"
            )

        if not self.config.conn:
            raise MCPServerError(f"No connection config for PostgreSQL server {self.server_id}")

        url_env = self.config.conn.url_env
        conn_url = os.getenv(url_env)

        if not conn_url:
            raise MCPServerError(
                f"Environment variable {url_env} not set for PostgreSQL server {self.server_id}"
            )

        try:
            self._pg_pool = await asyncpg.create_pool(
                conn_url,
                min_size=1,
                max_size=5,
                timeout=self.config.limits.timeout_s,
            )

            # Discover PostgreSQL "tools" (common query operations)
            await self._discover_postgres_tools()

        except Exception as e:
            raise MCPServerError(f"Failed to connect to PostgreSQL: {e}") from e

    async def _discover_postgres_tools(self) -> None:
        """Discover available PostgreSQL tools (query operations)."""
        # Define standard PostgreSQL query tools
        self._tools = {
            "query": MCPTool(
                name="query",
                description="Execute a SELECT query on the database",
                input_schema=MCPToolSchema(
                    type="object",
                    properties={
                        "sql": {
                            "type": "string",
                            "description": "SQL SELECT query to execute",
                        },
                        "params": {
                            "type": "array",
                            "description": "Query parameters for parameterized queries",
                            "items": {"type": "string"},
                        },
                    },
                    required=["sql"],
                ),
                server_id=self.server_id,
            ),
            "list_tables": MCPTool(
                name="list_tables",
                description="List all tables in the database",
                input_schema=MCPToolSchema(
                    type="object",
                    properties={
                        "schema": {
                            "type": "string",
                            "description": "Database schema name (default: public)",
                        },
                    },
                    required=[],
                ),
                server_id=self.server_id,
            ),
        }

    def get_tools(self) -> list[MCPTool]:
        """Get list of available tools from this server.

        Returns:
            List of tool definitions
        """
        return list(self._tools.values())

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPToolResult:
        """Execute a tool on this MCP server.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool input arguments

        Returns:
            Tool execution result

        Raises:
            MCPServerError: If server is not started or tool is not found
        """
        if not self._started:
            raise MCPServerError(f"Server {self.server_id} is not started")

        if tool_name not in self._tools:
            return MCPToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found on server {self.server_id}",
            )

        start_time = time.time()

        try:
            if self.config.type == "postgres":
                result = await self._execute_postgres_tool(tool_name, arguments)
            else:
                result = await self._execute_mcp_tool(tool_name, arguments)

            execution_time = time.time() - start_time
            result.metadata["execution_time_s"] = execution_time
            result.metadata["server_id"] = self.server_id

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            return MCPToolResult(
                success=False,
                error=f"Tool execution failed: {str(e)}",
                metadata={
                    "execution_time_s": execution_time,
                    "server_id": self.server_id,
                },
            )

    async def _cleanup_process(self) -> None:
        if self._process is not None:
            if self._process.returncode is None:
                self._process.kill()
            with contextlib.suppress(Exception):  # noqa: BLE001
                await self._process.wait()
        self._process = None
        self._stdin = None
        self._stdout = None
        self._stderr = None
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stderr_task
            self._stderr_task = None

    def _next_message_id(self) -> int:
        self._rpc_counter += 1
        return self._rpc_counter

    async def _write_message(self, message: dict[str, Any]) -> None:
        if not self._stdin:
            raise MCPServerError("MCP server stdin is not available")
        try:
            payload = json.dumps(message, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise MCPServerError(f"Failed to encode MCP message: {exc}") from exc

        self._stdin.write(payload.encode("utf-8") + b"\n")
        await self._stdin.drain()

    async def _read_message(self, timeout: float) -> dict[str, Any]:
        if not self._stdout:
            raise MCPServerError("MCP server stdout is not available")

        try:
            line = await asyncio.wait_for(self._stdout.readline(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise MCPServerError("Timed out waiting for MCP server response") from exc

        if not line:
            raise MCPServerError("MCP server closed the connection")

        try:
            payload = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as exc:  # noqa: BLE001
            raise MCPServerError(f"Failed to decode MCP response: {exc}") from exc

        if not isinstance(payload, dict):
            raise MCPServerError("Invalid MCP response payload")

        return cast(dict[str, Any], payload)

    async def _send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._process or not self._stdin or not self._stdout:
            raise MCPServerError("MCP server process is not running")

        request_id = self._next_message_id()
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params:
            message["params"] = params

        timeout = max(float(self.config.limits.timeout_s), 1.0)

        async with self._io_lock:
            await self._write_message(message)
            while True:
                response = await self._read_message(timeout)
                if response.get("id") == request_id:
                    return response

                # Handle notifications or unrelated responses gracefully
                if "method" in response and "id" not in response:
                    logger.debug(
                        "Received MCP notification from %s: %s",
                        self.server_id,
                        response.get("method"),
                    )
                    continue

                logger.debug(
                    "Ignoring unrelated MCP message from %s: %s",
                    self.server_id,
                    response,
                )

    async def _send_notification(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        if not self._stdin:
            raise MCPServerError("MCP server stdin is not available")

        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            message["params"] = params

        async with self._io_lock:
            await self._write_message(message)

    def _register_tools_from_payload(self, tools_payload: list[dict[str, Any]]) -> None:
        self._tools.clear()
        for raw_tool in tools_payload or []:
            name = raw_tool.get("name")
            if not isinstance(name, str):
                continue

            description = raw_tool.get("description", "")
            input_schema_payload = raw_tool.get("inputSchema", {}) or {}

            schema = MCPToolSchema(
                type=input_schema_payload.get("type", "object"),
                properties=input_schema_payload.get("properties", {}),
                required=input_schema_payload.get("required", []),
            )

            tool = MCPTool(
                name=name,
                description=description,
                input_schema=schema,
                server_id=self.server_id,
            )
            self._tools[name] = tool

    async def _drain_stderr(self) -> None:
        if not self._stderr:
            return
        try:
            while True:
                line = await self._stderr.readline()
                if not line:
                    break
                logger.debug(
                    "MCP[%s] stderr: %s",
                    self.server_id,
                    line.decode(errors="ignore").rstrip(),
                )
        except Exception as exc:  # noqa: BLE001
            # Best-effort logging only; surface trace for debugging without failing pipeline
            logger.debug("Failed to drain MCP stderr for %s", self.server_id, exc_info=exc)

    async def _execute_mcp_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPToolResult:
        if not self._process or not self._stdin or not self._stdout:
            return MCPToolResult(success=False, error="MCP server process is not running")

        try:
            response = await self._send_request(
                "tools/call",
                {"name": tool_name, "arguments": arguments or {}},
            )
        except MCPServerError as exc:
            return MCPToolResult(success=False, error=str(exc))

        if "error" in response:
            error_payload = response.get("error")
            if isinstance(error_payload, dict):
                message = error_payload.get("message") or error_payload.get("data")
            else:
                message = str(error_payload)
            return MCPToolResult(success=False, error=message or "MCP tool call failed")

        result_payload = response.get("result", {})
        success = result_payload.get("success")
        if success is None:
            success = result_payload.get("error") is None

        metadata = {
            key: value
            for key, value in result_payload.items()
            if key not in {"success", "output", "error"}
        }

        return MCPToolResult(
            success=bool(success),
            output=result_payload.get("output"),
            error=result_payload.get("error"),
            metadata={"raw_result": result_payload, **metadata},
        )

    async def _execute_postgres_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPToolResult:
        """Execute a PostgreSQL tool.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        if not self._pg_pool:
            return MCPToolResult(
                success=False,
                error="PostgreSQL connection pool not initialized",
            )

        try:
            async with self._pg_pool.acquire() as conn:
                if tool_name == "query":
                    sql = arguments.get("sql", "")
                    params = arguments.get("params", [])

                    # Validate that query is read-only (SELECT only)
                    if not sql.strip().upper().startswith("SELECT"):
                        return MCPToolResult(
                            success=False,
                            error="Only SELECT queries are allowed in read-only mode",
                        )

                    rows = await conn.fetch(sql, *params)
                    result_data = [dict(row) for row in rows]

                    return MCPToolResult(
                        success=True,
                        output={"rows": result_data, "count": len(result_data)},
                    )

                elif tool_name == "list_tables":
                    schema = arguments.get("schema", "public")
                    sql = """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = $1
                        ORDER BY table_name
                    """
                    rows = await conn.fetch(sql, schema)
                    tables = [row["table_name"] for row in rows]

                    return MCPToolResult(
                        success=True,
                        output={"tables": tables, "count": len(tables)},
                    )

                else:
                    return MCPToolResult(
                        success=False,
                        error=f"Unknown PostgreSQL tool: {tool_name}",
                    )

        except Exception as e:
            return MCPToolResult(
                success=False,
                error=f"PostgreSQL execution error: {str(e)}",
            )
