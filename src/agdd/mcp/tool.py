"""MCP Tool definitions and execution.

This module provides the abstraction for MCP tools, including
JSON Schema definitions and execution interfaces.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MCPToolParameter(BaseModel):
    """JSON Schema definition for a tool parameter."""

    type: str = Field(
        description="JSON Schema type (string, number, boolean, object, array)",
    )
    description: str | None = Field(
        default=None,
        description="Human-readable description of the parameter",
    )
    enum: list[Any] | None = Field(
        default=None,
        description="Allowed values for enumerated parameters",
    )
    properties: dict[str, Any] | None = Field(
        default=None,
        description="Properties for object-type parameters",
    )
    items: dict[str, Any] | None = Field(
        default=None,
        description="Item schema for array-type parameters",
    )
    required: list[str] | None = Field(
        default=None,
        description="Required properties for object-type parameters",
    )


class MCPToolSchema(BaseModel):
    """JSON Schema definition for a tool's input parameters."""

    type: str = Field(
        default="object",
        description="Schema type (typically 'object')",
    )
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool parameter definitions",
    )
    required: list[str] = Field(
        default_factory=list,
        description="List of required parameter names",
    )


class MCPTool(BaseModel):
    """Represents a tool provided by an MCP server.

    This abstraction allows skills to discover and invoke tools
    from MCP servers in a standardized way.
    """

    name: str = Field(
        description="Unique tool name",
    )
    description: str = Field(
        description="Human-readable description of the tool's functionality",
    )
    input_schema: MCPToolSchema = Field(
        description="JSON Schema for tool input parameters",
    )
    server_id: str = Field(
        description="ID of the MCP server providing this tool",
    )

    def get_qualified_name(self) -> str:
        """Get the fully qualified tool name.

        Returns:
            Tool name in format "server_id.tool_name"
        """
        return f"{self.server_id}.{self.name}"


class MCPToolResult(BaseModel):
    """Result from executing an MCP tool."""

    success: bool = Field(
        description="Whether the tool execution succeeded",
    )
    output: Any = Field(
        default=None,
        description="Tool output data (structure depends on the tool)",
    )
    error: str | None = Field(
        default=None,
        description="Error message if execution failed",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (execution time, server info, etc.)",
    )
