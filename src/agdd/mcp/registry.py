"""MCP Registry for auto-discovery and server management.

This module provides centralized management of all MCP servers,
including auto-discovery from .mcp/servers/*.yaml files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from agdd.mcp.config import MCPServerConfig
from agdd.mcp.server import MCPServer
from agdd.mcp.tool import MCPTool, MCPToolResult

logger = logging.getLogger(__name__)


class MCPRegistryError(Exception):
    """Base exception for MCP registry errors."""

    pass


class MCPRegistry:
    """Central registry for all MCP servers.

    This class handles:
    - Auto-discovery of MCP server configurations from .mcp/servers/
    - Lifecycle management of server connections
    - Permission validation for skill access
    - Tool discovery and routing
    """

    def __init__(self, servers_dir: Path | None = None) -> None:
        """Initialize MCP registry.

        Args:
            servers_dir: Directory containing server YAML configs.
                        Defaults to .mcp/servers/ in project root.
        """
        self._servers: dict[str, MCPServer] = {}
        self._configs: dict[str, MCPServerConfig] = {}
        self._servers_dir = servers_dir or Path.cwd() / ".mcp" / "servers"

    def discover_servers(self) -> None:
        """Discover and load all MCP server configurations.

        This method scans the servers directory for *.yaml files
        and loads their configurations.

        Raises:
            MCPRegistryError: If discovery or loading fails
        """
        if not self._servers_dir.exists():
            logger.warning(f"MCP servers directory not found: {self._servers_dir}")
            return

        if not self._servers_dir.is_dir():
            raise MCPRegistryError(f"Not a directory: {self._servers_dir}")

        yaml_files = list(self._servers_dir.glob("*.yaml"))
        logger.info(f"Discovering MCP servers from {len(yaml_files)} config files")

        for yaml_file in yaml_files:
            try:
                self._load_server_config(yaml_file)
            except Exception as e:
                logger.error(f"Failed to load config {yaml_file}: {e}")
                # Continue with other configs

        logger.info(f"Discovered {len(self._configs)} MCP servers")

    def _load_server_config(self, yaml_file: Path) -> None:
        """Load a single server configuration file.

        Args:
            yaml_file: Path to YAML configuration file

        Raises:
            MCPRegistryError: If loading or validation fails
        """
        with open(yaml_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise MCPRegistryError(f"Empty configuration file: {yaml_file}")

        config = MCPServerConfig(**data)
        config.validate_type_fields()

        if config.server_id in self._configs:
            logger.warning(f"Duplicate server ID '{config.server_id}', overwriting")

        self._configs[config.server_id] = config
        logger.debug(f"Loaded config for server: {config.server_id}")

    async def start_server(self, server_id: str) -> None:
        """Start a specific MCP server.

        Args:
            server_id: ID of the server to start

        Raises:
            MCPRegistryError: If server not found or fails to start
        """
        if server_id not in self._configs:
            raise MCPRegistryError(f"Server '{server_id}' not found in registry")

        if server_id in self._servers and self._servers[server_id].is_started:
            logger.debug(f"Server '{server_id}' already started")
            return

        config = self._configs[server_id]
        server = MCPServer(config)

        try:
            await server.start()
            self._servers[server_id] = server
            logger.info(f"Started MCP server: {server_id}")
        except Exception as e:
            raise MCPRegistryError(f"Failed to start server '{server_id}': {e}") from e

    async def stop_server(self, server_id: str) -> None:
        """Stop a specific MCP server.

        Args:
            server_id: ID of the server to stop
        """
        if server_id not in self._servers:
            logger.debug(f"Server '{server_id}' not running")
            return

        server = self._servers[server_id]
        await server.stop()
        del self._servers[server_id]
        logger.info(f"Stopped MCP server: {server_id}")

    async def start_all_servers(self) -> None:
        """Start all discovered MCP servers."""
        logger.info(f"Starting {len(self._configs)} MCP servers")

        for server_id in self._configs:
            try:
                await self.start_server(server_id)
            except Exception as e:
                logger.error(f"Failed to start server '{server_id}': {e}")
                # Continue with other servers

    async def stop_all_servers(self) -> None:
        """Stop all running MCP servers."""
        logger.info(f"Stopping {len(self._servers)} MCP servers")

        server_ids = list(self._servers.keys())
        for server_id in server_ids:
            try:
                await self.stop_server(server_id)
            except Exception as e:
                logger.error(f"Failed to stop server '{server_id}': {e}")

    def get_server(self, server_id: str) -> MCPServer | None:
        """Get a running MCP server by ID.

        Args:
            server_id: Server ID to look up

        Returns:
            MCPServer instance if running, None otherwise
        """
        return self._servers.get(server_id)

    def list_servers(self) -> list[str]:
        """Get list of all discovered server IDs.

        Returns:
            List of server IDs
        """
        return list(self._configs.keys())

    def list_running_servers(self) -> list[str]:
        """Get list of currently running server IDs.

        Returns:
            List of running server IDs
        """
        return list(self._servers.keys())

    def get_tools(self, server_id: str | None = None) -> list[MCPTool]:
        """Get available tools from MCP servers.

        Args:
            server_id: Optional server ID to filter by.
                      If None, returns tools from all running servers.

        Returns:
            List of available tools
        """
        if server_id:
            server = self._servers.get(server_id)
            return server.get_tools() if server else []

        all_tools: list[MCPTool] = []
        for server in self._servers.values():
            all_tools.extend(server.get_tools())

        return all_tools

    def validate_permissions(
        self,
        requested_permissions: list[str],
    ) -> dict[str, bool]:
        """Validate requested permissions against available servers.

        Args:
            requested_permissions: List of permissions in format "mcp:<server_id>"

        Returns:
            Dictionary mapping permission to availability status
        """
        results: dict[str, bool] = {}

        for perm in requested_permissions:
            if not perm.startswith("mcp:"):
                results[perm] = False
                continue

            server_id = perm[4:]  # Remove "mcp:" prefix
            results[perm] = server_id in self._configs

        return results

    async def execute_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        required_permissions: list[str] | None = None,
    ) -> MCPToolResult:
        """Execute a tool on an MCP server with permission validation.

        Args:
            server_id: ID of the server providing the tool
            tool_name: Name of the tool to execute
            arguments: Tool input arguments
            required_permissions: Optional list of required permissions to validate

        Returns:
            Tool execution result
        """
        # Validate permissions if provided
        if required_permissions:
            validation = self.validate_permissions(required_permissions)
            missing = [p for p, valid in validation.items() if not valid]
            if missing:
                return MCPToolResult(
                    success=False,
                    error=f"Missing required permissions: {', '.join(missing)}",
                )

        # Ensure server is started
        if server_id not in self._servers:
            try:
                await self.start_server(server_id)
            except MCPRegistryError as e:
                return MCPToolResult(
                    success=False,
                    error=str(e),
                )

        # Execute tool
        server = self._servers[server_id]
        return await server.execute_tool(tool_name, arguments)
