"""MCP Runtime for skills integration.

This module provides the runtime interface for skills to access
MCP tools with proper permission enforcement.
"""

from __future__ import annotations

import logging
from typing import Any

from agdd.mcp.registry import MCPRegistry
from agdd.mcp.tool import MCPTool, MCPToolResult

logger = logging.getLogger(__name__)


class MCPRuntimeError(Exception):
    """Base exception for MCP runtime errors."""

    pass


class MCPRuntime:
    """Runtime interface for skills to access MCP tools.

    This class provides a controlled interface for skills to
    discover and execute MCP tools, with permission enforcement.
    """

    def __init__(self, registry: MCPRegistry) -> None:
        """Initialize MCP runtime.

        Args:
            registry: MCP registry managing server connections
        """
        self._registry = registry
        self._granted_permissions: set[str] = set()

    def grant_permissions(self, permissions: list[str]) -> None:
        """Grant permissions to this runtime instance.

        This method should be called when initializing the runtime
        for a specific skill, based on the skill's declared permissions.

        Args:
            permissions: List of permissions in format "mcp:<server_id>"
        """
        self._granted_permissions.update(permissions)
        logger.debug(f"Granted permissions: {permissions}")

    def revoke_permissions(self, permissions: list[str]) -> None:
        """Revoke previously granted permissions.

        Args:
            permissions: List of permissions to revoke
        """
        self._granted_permissions.difference_update(permissions)
        logger.debug(f"Revoked permissions: {permissions}")

    def get_granted_permissions(self) -> list[str]:
        """Get list of currently granted permissions.

        Returns:
            List of granted permission strings
        """
        return list(self._granted_permissions)

    def list_available_tools(self) -> list[MCPTool]:
        """List all tools available with current permissions.

        Returns:
            List of tools from servers this runtime has permission to access
        """
        available_tools: list[MCPTool] = []

        for permission in self._granted_permissions:
            if not permission.startswith("mcp:"):
                continue

            server_id = permission[4:]  # Remove "mcp:" prefix
            tools = self._registry.get_tools(server_id)
            available_tools.extend(tools)

        return available_tools

    def check_permission(self, server_id: str) -> bool:
        """Check if runtime has permission to access a server.

        Args:
            server_id: ID of the server to check

        Returns:
            True if permission is granted, False otherwise
        """
        permission = f"mcp:{server_id}"
        return permission in self._granted_permissions

    async def execute_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPToolResult:
        """Execute an MCP tool with permission enforcement.

        Args:
            server_id: ID of the server providing the tool
            tool_name: Name of the tool to execute
            arguments: Tool input arguments

        Returns:
            Tool execution result

        Raises:
            MCPRuntimeError: If permission is denied
        """
        # Check permission
        if not self.check_permission(server_id):
            error_msg = (
                f"Permission denied: skill does not have access to server '{server_id}'. "
                f"Required permission: mcp:{server_id}"
            )
            logger.warning(error_msg)
            return MCPToolResult(
                success=False,
                error=error_msg,
            )

        # Execute tool via registry
        logger.info(f"Executing tool {server_id}.{tool_name}")
        result = await self._registry.execute_tool(
            server_id=server_id,
            tool_name=tool_name,
            arguments=arguments,
            required_permissions=list(self._granted_permissions),
        )

        if result.success:
            logger.info(f"Tool execution succeeded: {server_id}.{tool_name}")
        else:
            logger.warning(f"Tool execution failed: {server_id}.{tool_name} - {result.error}")

        return result

    async def query_postgres(
        self,
        server_id: str,
        sql: str,
        params: list[Any] | None = None,
    ) -> MCPToolResult:
        """Convenience method for executing PostgreSQL queries.

        Args:
            server_id: ID of the PostgreSQL server
            sql: SQL SELECT query
            params: Optional query parameters

        Returns:
            Query result
        """
        arguments: dict[str, Any] = {"sql": sql}
        if params:
            arguments["params"] = params

        return await self.execute_tool(
            server_id=server_id,
            tool_name="query",
            arguments=arguments,
        )

    async def list_postgres_tables(
        self,
        server_id: str,
        schema: str = "public",
    ) -> MCPToolResult:
        """Convenience method for listing PostgreSQL tables.

        Args:
            server_id: ID of the PostgreSQL server
            schema: Database schema name (default: public)

        Returns:
            List of tables
        """
        return await self.execute_tool(
            server_id=server_id,
            tool_name="list_tables",
            arguments={"schema": schema},
        )
