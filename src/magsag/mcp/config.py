"""MCP Server configuration data models.

This module defines the data models for MCP server configurations,
which are loaded from .mcp/servers/*.yaml files.
"""

from __future__ import annotations

from typing import Dict, Literal

from pydantic import BaseModel, Field


class MCPLimits(BaseModel):
    """Rate limits and timeout configuration for MCP server."""

    rate_per_min: int = Field(
        default=60,
        description="Maximum requests per minute",
        gt=0,
    )
    timeout_s: int = Field(
        default=30,
        description="Request timeout in seconds",
        gt=0,
    )


class PostgresConnection(BaseModel):
    """PostgreSQL connection configuration."""

    url_env: str = Field(
        description="Environment variable name containing connection URL",
    )


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server.

    This model represents the structure of .mcp/servers/*.yaml files.
    """

    server_id: str = Field(
        description="Unique identifier for the MCP server",
    )
    type: Literal["mcp", "postgres"] = Field(
        description="Server type: mcp for stdio MCP servers, postgres for database",
    )
    description: str | None = Field(
        default=None,
        description="Human-readable description of the server",
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="Access scopes granted to this server (e.g., read:files)",
    )
    limits: MCPLimits = Field(
        default_factory=MCPLimits,
        description="Rate limits and timeout configuration",
    )
    transport: Literal["stdio", "websocket", "http"] | None = Field(
        default=None,
        description="Transport override: stdio (default), websocket, or http",
    )
    url: str | None = Field(
        default=None,
        description="Endpoint URL for HTTP/WebSocket transports",
    )
    headers: Dict[str, str] = Field(
        default_factory=dict,
        description="Additional headers for HTTP/WebSocket transports",
    )

    # MCP server specific fields (type="mcp")
    command: str | None = Field(
        default=None,
        description="Command to execute for MCP server (e.g., npx)",
    )
    args: list[str] = Field(
        default_factory=list,
        description="Arguments for the MCP server command",
    )

    # PostgreSQL specific fields (type="postgres")
    conn: PostgresConnection | None = Field(
        default=None,
        description="PostgreSQL connection configuration",
    )

    def validate_type_fields(self) -> None:
        """Validate that required fields are present based on server type."""
        if self.type == "mcp":
            if (self.transport or "stdio") == "stdio" and not self.command:
                raise ValueError("STDIO MCP servers must specify 'command'")
            if self.transport in {"http", "websocket"}:
                if not self.url:
                    raise ValueError(
                        "HTTP/WebSocket MCP servers must specify 'url' field"
                    )
        elif self.type == "postgres":
            if not self.conn:
                raise ValueError("PostgreSQL servers must specify 'conn' field")

    def get_permission_name(self) -> str:
        """Get the permission name for this MCP server.

        Returns:
            Permission name in format "mcp:<server_id>"
        """
        return f"mcp:{self.server_id}"
