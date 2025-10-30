"""
A2A Protocol Types - JSON-RPC 2.0 compliant message types.

This module defines core types for Agent-to-Agent (A2A) communication
following the JSON-RPC 2.0 specification with extensions for agent metadata,
discovery, and authentication/authorization hooks.

## Protocol Versioning

A2A protocol types follow semantic versioning (SemVer) for schema evolution:

**Schema Version**: 1.0.0

**Backward Compatibility Policy**:
- **Adding optional fields**: Minor version bump (e.g., 1.0.0 -> 1.1.0)
- **Removing fields**: Major version bump (e.g., 1.0.0 -> 2.0.0)
- **Changing field types**: Major version bump (e.g., 1.0.0 -> 2.0.0)
- **Bug fixes/clarifications**: Patch version bump (e.g., 1.0.0 -> 1.0.1)

Clients should ignore unknown fields for forward compatibility.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# A2A Protocol Schema Version
A2A_SCHEMA_VERSION = "1.0.0"


# JSON-RPC 2.0 Core Types


class JsonRpcRequest(BaseModel):
    """
    JSON-RPC 2.0 Request.

    Represents a remote procedure call request from one agent to another.
    """

    jsonrpc: Literal["2.0"] = "2.0"
    method: str = Field(..., description="Method name to invoke")
    params: dict[str, Any] | list[Any] | None = Field(
        None, description="Method parameters (object or array)"
    )
    id: str | int | None = Field(None, description="Request identifier (null for notifications)")

    # Extension point: signature/authorization metadata
    meta: dict[str, Any] | None = Field(
        None,
        description="Optional metadata for signatures, timestamps, auth tokens",
    )


class JsonRpcError(BaseModel):
    """
    JSON-RPC 2.0 Error object.

    Standard error codes:
    - -32700: Parse error
    - -32600: Invalid Request
    - -32601: Method not found
    - -32602: Invalid params
    - -32603: Internal error
    - -32000 to -32099: Server error (implementation-defined)
    """

    model_config = ConfigDict(extra="forbid")

    code: int = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    data: Any | None = Field(default=None, description="Additional error data")


class JsonRpcResponse(BaseModel):
    """
    JSON-RPC 2.0 Response.

    Either contains a result (success) or an error (failure).
    """

    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    result: Any | None = None
    error: JsonRpcError | None = None
    id: str | int | None = Field(..., description="Request identifier")

    # Extension point: signature/authorization metadata
    meta: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata for signatures, timestamps",
    )


# A2A Protocol-Specific Types


class Capability(BaseModel):
    """
    Agent capability descriptor.

    Describes a method or service that an agent provides.
    """

    name: str = Field(..., description="Capability/method name")
    description: str | None = Field(None, description="Human-readable description")
    input_schema: dict[str, Any] | None = Field(
        None, description="JSON Schema for input parameters"
    )
    output_schema: dict[str, Any] | None = Field(None, description="JSON Schema for output/result")


class AgentEndpoint(BaseModel):
    """
    Agent communication endpoint.

    Defines how to reach an agent (e.g., HTTP URL, message queue).
    """

    protocol: str = Field(..., description="Protocol type (http, amqp, grpc, etc.)")
    uri: str = Field(..., description="Endpoint URI")
    metadata: dict[str, Any] | None = Field(None, description="Protocol-specific metadata")


class AgentIdentity(BaseModel):
    """
    Agent identity information.

    Represents the unique identity of an agent in the A2A network.
    """

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Human-readable agent name")
    version: str = Field(..., description="Agent version (semver recommended)")

    # Extension point: public key for signature verification
    public_key: str | None = Field(
        default=None, description="Public key (PEM format) for signature verification"
    )


class AgentMetadata(BaseModel):
    """
    Extended agent metadata.

    Additional information about agent's purpose, owner, and runtime.
    """

    description: str | None = Field(None, description="Agent description")
    owner: str | None = Field(None, description="Owner/organization")
    tags: list[str] = Field(default_factory=list, description="Searchable tags")
    documentation_url: str | None = Field(None, description="Documentation URL")
    created_at: str | None = Field(None, description="Creation timestamp (ISO 8601)")
    updated_at: str | None = Field(None, description="Last update timestamp (ISO 8601)")


# Standard JSON-RPC Error Codes

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
SERVER_ERROR_MIN = -32000
SERVER_ERROR_MAX = -32099

# A2A-specific error codes (using server error range)
AGENT_NOT_FOUND = -32001
DISCOVERY_ERROR = -32002
AUTHENTICATION_FAILED = -32003
AUTHORIZATION_FAILED = -32004
SIGNATURE_INVALID = -32005
