"""MCP Server connection management.

This module handles connections to individual MCP servers,
including lifecycle management and tool execution.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any

from agdd.mcp.config import MCPServerConfig
from agdd.mcp.tool import MCPTool, MCPToolResult, MCPToolSchema

# Optional import for PostgreSQL support
try:
    import asyncpg  # type: ignore[import-untyped]

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
        self._process: subprocess.Popen[bytes] | None = None
        self._tools: dict[str, MCPTool] = {}
        self._pg_pool: Any = None  # asyncpg.Pool[Any] | None (if asyncpg is installed)
        self._started: bool = False

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
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

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
        pass

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
                # Placeholder for MCP protocol tool execution
                result = MCPToolResult(
                    success=False,
                    error="MCP protocol not yet implemented",
                )

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
