"""
A2A Protocol - Agent-to-Agent Communication Protocol.

This module implements the A2A (Agent-to-Agent) protocol for agent discovery,
capability exchange, and JSON-RPC 2.0 compliant communication. It provides
a foundation for building distributed agent systems with support for:

- Agent identity and capability descriptors (AgentCard)
- Service discovery and registration
- JSON-RPC 2.0 message exchange
- Extension points for authentication and authorization

Example Usage:

    # Create an agent card
    from agdd.protocols.a2a import AgentCardBuilder, AgentCard

    card = (
        AgentCardBuilder("agent-001", "MyAgent", "1.0.0")
        .add_capability("process_data", description="Process data inputs")
        .add_endpoint("http", "http://localhost:8080/rpc")
        .with_metadata(description="Data processing agent", tags=["data", "processing"])
        .build()
    )

    # Register with discovery
    from agdd.protocols.a2a import DiscoveryClient

    discovery = DiscoveryClient()
    discovery.register(card)

    # Find agents by capability
    agents = discovery.find_agents_by_capability("process_data")

    # Create JSON-RPC client/server
    from agdd.protocols.a2a import A2AClient, A2AServer

    # Server side
    server = A2AServer()
    server.register_method("echo", lambda message: {"echo": message})

    # Client side
    client = A2AClient()
    request = client.create_request("echo", {"message": "hello"})
"""

# Agent Card and Builder
from .agent_card import AgentCard, AgentCardBuilder

# Communication
from .communication import (
    A2AClient,
    A2AServer,
    MessageHandler,
    RequestMiddleware,
)

# Discovery
from .discovery import (
    DiscoveryClient,
    DiscoveryRegistry,
    InMemoryDiscovery,
)

# Types
from .types import (
    AGENT_NOT_FOUND,
    AUTHENTICATION_FAILED,
    AUTHORIZATION_FAILED,
    DISCOVERY_ERROR,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    SERVER_ERROR_MAX,
    SERVER_ERROR_MIN,
    SIGNATURE_INVALID,
    AgentEndpoint,
    AgentIdentity,
    AgentMetadata,
    Capability,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
)

__all__ = [
    # Agent Card
    "AgentCard",
    "AgentCardBuilder",
    # Communication
    "A2AClient",
    "A2AServer",
    "MessageHandler",
    "RequestMiddleware",
    # Discovery
    "DiscoveryClient",
    "DiscoveryRegistry",
    "InMemoryDiscovery",
    # Types - Core
    "JsonRpcRequest",
    "JsonRpcResponse",
    "JsonRpcError",
    # Types - Agent
    "AgentIdentity",
    "AgentEndpoint",
    "AgentMetadata",
    "Capability",
    # Error Codes
    "PARSE_ERROR",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "INVALID_PARAMS",
    "INTERNAL_ERROR",
    "SERVER_ERROR_MIN",
    "SERVER_ERROR_MAX",
    "AGENT_NOT_FOUND",
    "DISCOVERY_ERROR",
    "AUTHENTICATION_FAILED",
    "AUTHORIZATION_FAILED",
    "SIGNATURE_INVALID",
]

__version__ = "0.1.0"
