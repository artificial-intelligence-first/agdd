"""MCP (Model Context Protocol) integration for AGDD.

This module provides standardized access to MCP servers and tools,
with auto-discovery, permission management, and execution runtime.

Key components:
- MCPRegistry: Auto-discovers and manages MCP server connections
- MCPRuntime: Provides permission-enforced access for skills
- MCPServer: Manages individual server connections
- MCPTool: Represents tools provided by MCP servers

Usage:
    # Initialize registry and discover servers
    registry = MCPRegistry()
    registry.discover_servers()
    await registry.start_all_servers()

    # Create runtime for a skill with permissions
    runtime = MCPRuntime(registry)
    runtime.grant_permissions(["mcp:pg-readonly"])

    # Execute a tool
    result = await runtime.execute_tool(
        server_id="pg-readonly",
        tool_name="query",
        arguments={"sql": "SELECT * FROM users LIMIT 10"},
    )

    if result.success:
        print(result.output)
    else:
        print(f"Error: {result.error}")

    # Cleanup
    await registry.stop_all_servers()
"""

from agdd.mcp.config import MCPLimits, MCPServerConfig, PostgresConnection
from agdd.mcp.registry import MCPRegistry, MCPRegistryError
from agdd.mcp.runtime import MCPRuntime, MCPRuntimeError
from agdd.mcp.server import MCPServer, MCPServerError
from agdd.mcp.tool import (
    MCPTool,
    MCPToolParameter,
    MCPToolResult,
    MCPToolSchema,
)

__all__ = [
    # Configuration
    "MCPServerConfig",
    "MCPLimits",
    "PostgresConnection",
    # Server management
    "MCPServer",
    "MCPServerError",
    # Registry
    "MCPRegistry",
    "MCPRegistryError",
    # Runtime
    "MCPRuntime",
    "MCPRuntimeError",
    # Tools
    "MCPTool",
    "MCPToolSchema",
    "MCPToolParameter",
    "MCPToolResult",
]
