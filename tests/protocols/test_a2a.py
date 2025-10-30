"""
Tests for A2A Protocol - Agent-to-Agent Communication.

This test suite validates:
- JSON-RPC 2.0 compliance for request/response handling
- Agent card creation and validation
- Discovery and registration functionality
- Communication layer (client/server)
"""

from typing import Any

import pytest

from agdd.protocols.a2a import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    A2AClient,
    A2AServer,
    AgentCard,
    AgentCardBuilder,
    DiscoveryClient,
    InMemoryDiscovery,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
)


# ============================================================================
# Agent Card Tests
# ============================================================================


def test_agent_card_builder() -> None:
    """Test building an agent card with the builder pattern."""
    card = (
        AgentCardBuilder("agent-001", "TestAgent", "1.0.0")
        .add_capability("echo", description="Echo messages")
        .add_endpoint("http", "http://localhost:8080/rpc")
        .with_metadata(description="Test agent", tags=["test"])
        .build()
    )

    assert card.identity.agent_id == "agent-001"
    assert card.identity.name == "TestAgent"
    assert card.identity.version == "1.0.0"
    assert len(card.capabilities) == 1
    assert card.capabilities[0].name == "echo"
    assert len(card.endpoints) == 1
    assert card.endpoints[0].protocol == "http"
    assert card.metadata is not None
    assert card.metadata.tags == ["test"]


def test_agent_card_has_capability() -> None:
    """Test checking if agent has a capability."""
    card = (
        AgentCardBuilder("agent-001", "TestAgent", "1.0.0")
        .add_capability("echo")
        .add_capability("process")
        .build()
    )

    assert card.has_capability("echo") is True
    assert card.has_capability("process") is True
    assert card.has_capability("unknown") is False


def test_agent_card_get_capability() -> None:
    """Test retrieving a specific capability."""
    card = (
        AgentCardBuilder("agent-001", "TestAgent", "1.0.0")
        .add_capability("echo", description="Echo messages")
        .build()
    )

    cap = card.get_capability("echo")
    assert cap is not None
    assert cap.name == "echo"
    assert cap.description == "Echo messages"

    assert card.get_capability("unknown") is None


def test_agent_card_get_endpoint() -> None:
    """Test retrieving endpoint by protocol."""
    card = (
        AgentCardBuilder("agent-001", "TestAgent", "1.0.0")
        .add_endpoint("http", "http://localhost:8080")
        .add_endpoint("grpc", "grpc://localhost:9090")
        .build()
    )

    http_endpoint = card.get_endpoint("http")
    assert http_endpoint is not None
    assert http_endpoint.uri == "http://localhost:8080"

    grpc_endpoint = card.get_endpoint("grpc")
    assert grpc_endpoint is not None
    assert grpc_endpoint.uri == "grpc://localhost:9090"

    assert card.get_endpoint("amqp") is None


def test_agent_card_serialization() -> None:
    """Test agent card to/from dict conversion."""
    card = (
        AgentCardBuilder("agent-001", "TestAgent", "1.0.0")
        .add_capability("echo")
        .add_endpoint("http", "http://localhost:8080")
        .build()
    )

    # To dict
    card_dict = card.to_dict()
    assert card_dict["identity"]["agent_id"] == "agent-001"

    # From dict
    restored = AgentCard.from_dict(card_dict)
    assert restored.identity.agent_id == "agent-001"
    assert restored.has_capability("echo")


# ============================================================================
# Discovery Tests
# ============================================================================


def test_discovery_register_and_find() -> None:
    """Test agent registration and lookup by ID."""
    discovery = DiscoveryClient(InMemoryDiscovery())

    card = AgentCardBuilder("agent-001", "TestAgent", "1.0.0").build()
    discovery.register(card)

    found = discovery.find_agent("agent-001")
    assert found is not None
    assert found.identity.agent_id == "agent-001"


def test_discovery_register_duplicate_fails() -> None:
    """Test that registering duplicate agent fails."""
    discovery = DiscoveryClient(InMemoryDiscovery())

    card = AgentCardBuilder("agent-001", "TestAgent", "1.0.0").build()
    discovery.register(card)

    with pytest.raises(ValueError, match="already registered"):
        discovery.register(card)


def test_discovery_unregister() -> None:
    """Test agent unregistration."""
    discovery = DiscoveryClient(InMemoryDiscovery())

    card = AgentCardBuilder("agent-001", "TestAgent", "1.0.0").build()
    discovery.register(card)

    discovery.unregister("agent-001")

    found = discovery.find_agent("agent-001")
    assert found is None


def test_discovery_find_by_capability() -> None:
    """Test finding agents by capability."""
    discovery = DiscoveryClient(InMemoryDiscovery())

    card1 = (
        AgentCardBuilder("agent-001", "Agent1", "1.0.0")
        .add_capability("echo")
        .add_capability("process")
        .build()
    )
    card2 = AgentCardBuilder("agent-002", "Agent2", "1.0.0").add_capability("echo").build()
    card3 = AgentCardBuilder("agent-003", "Agent3", "1.0.0").build()

    discovery.register(card1)
    discovery.register(card2)
    discovery.register(card3)

    # Find by echo capability
    echo_agents = discovery.find_agents_by_capability("echo")
    assert len(echo_agents) == 2
    agent_ids = {a.identity.agent_id for a in echo_agents}
    assert agent_ids == {"agent-001", "agent-002"}

    # Find by process capability
    process_agents = discovery.find_agents_by_capability("process")
    assert len(process_agents) == 1
    assert process_agents[0].identity.agent_id == "agent-001"

    # Find non-existent capability
    unknown_agents = discovery.find_agents_by_capability("unknown")
    assert len(unknown_agents) == 0


def test_discovery_find_by_tags() -> None:
    """Test finding agents by tags."""
    discovery = DiscoveryClient(InMemoryDiscovery())

    card1 = (
        AgentCardBuilder("agent-001", "Agent1", "1.0.0")
        .with_metadata(tags=["data", "processing"])
        .build()
    )
    card2 = (
        AgentCardBuilder("agent-002", "Agent2", "1.0.0")
        .with_metadata(tags=["data", "storage"])
        .build()
    )
    card3 = AgentCardBuilder("agent-003", "Agent3", "1.0.0").with_metadata(tags=["ui"]).build()

    discovery.register(card1)
    discovery.register(card2)
    discovery.register(card3)

    # Find by "data" tag
    data_agents = discovery.find_agents_by_tags(["data"])
    assert len(data_agents) == 2
    agent_ids = {a.identity.agent_id for a in data_agents}
    assert agent_ids == {"agent-001", "agent-002"}

    # Find by multiple tags (OR logic)
    ui_or_storage = discovery.find_agents_by_tags(["ui", "storage"])
    assert len(ui_or_storage) == 2
    agent_ids = {a.identity.agent_id for a in ui_or_storage}
    assert agent_ids == {"agent-002", "agent-003"}


def test_discovery_list_all() -> None:
    """Test listing all registered agents."""
    discovery = DiscoveryClient(InMemoryDiscovery())

    card1 = AgentCardBuilder("agent-001", "Agent1", "1.0.0").build()
    card2 = AgentCardBuilder("agent-002", "Agent2", "1.0.0").build()

    discovery.register(card1)
    discovery.register(card2)

    all_agents = discovery.list_agents()
    assert len(all_agents) == 2


def test_discovery_query_multiple_criteria() -> None:
    """Test querying with multiple criteria (AND logic)."""
    discovery = DiscoveryClient(InMemoryDiscovery())

    card1 = (
        AgentCardBuilder("agent-001", "Agent1", "1.0.0")
        .add_capability("echo")
        .with_metadata(tags=["data"])
        .build()
    )
    card2 = (
        AgentCardBuilder("agent-002", "Agent2", "1.0.0")
        .add_capability("echo")
        .with_metadata(tags=["ui"])
        .build()
    )
    card3 = (
        AgentCardBuilder("agent-003", "Agent3", "1.0.0")
        .add_capability("process")
        .with_metadata(tags=["data"])
        .build()
    )

    discovery.register(card1)
    discovery.register(card2)
    discovery.register(card3)

    # Query: capability=echo AND tags=data
    results = discovery.query(capability="echo", tags=["data"])
    assert len(results) == 1
    assert results[0].identity.agent_id == "agent-001"


# ============================================================================
# JSON-RPC Communication Tests
# ============================================================================


def test_jsonrpc_request_creation() -> None:
    """Test creating JSON-RPC requests."""
    request = JsonRpcRequest(method="echo", params={"message": "hello"}, id="req-001", meta=None)

    assert request.jsonrpc == "2.0"
    assert request.method == "echo"
    assert request.params == {"message": "hello"}
    assert request.id == "req-001"


def test_jsonrpc_notification() -> None:
    """Test creating JSON-RPC notifications (id=None)."""
    notification = JsonRpcRequest(method="notify", params={"event": "started"}, id=None, meta=None)

    assert notification.id is None  # Notification has no ID


def test_jsonrpc_response_success() -> None:
    """Test creating successful JSON-RPC response."""
    response = JsonRpcResponse(id="req-001", result={"echo": "hello"})

    assert response.jsonrpc == "2.0"
    assert response.id == "req-001"
    assert response.result == {"echo": "hello"}
    assert response.error is None


def test_jsonrpc_response_error() -> None:
    """Test creating error JSON-RPC response."""
    error = JsonRpcError(code=METHOD_NOT_FOUND, message="Method not found")
    response = JsonRpcResponse(id="req-001", error=error)

    assert response.jsonrpc == "2.0"
    assert response.id == "req-001"
    assert response.result is None
    assert response.error is not None
    assert response.error.code == METHOD_NOT_FOUND


def test_a2a_server_method_registration() -> None:
    """Test registering methods with A2A server."""
    server = A2AServer()

    def echo_handler(message: str) -> dict[str, str]:
        return {"echo": message}

    server.register_method("echo", echo_handler)

    request = JsonRpcRequest(method="echo", params={"message": "hello"}, id="req-001", meta=None)
    response = server.handle_request(request)
    assert response is not None

    assert response.id == "req-001"
    assert response.result == {"echo": "hello"}
    assert response.error is None


def test_a2a_server_method_not_found() -> None:
    """Test calling non-existent method returns error."""
    server = A2AServer()

    request = JsonRpcRequest(method="unknown", params={}, id="req-001", meta=None)
    response = server.handle_request(request)
    assert response is not None

    assert response.error is not None
    assert response.error.code == METHOD_NOT_FOUND
    assert "not found" in response.error.message.lower()


def test_a2a_server_invalid_params() -> None:
    """Test calling method with invalid params."""
    server = A2AServer()

    def add_handler(a: int, b: int) -> int:
        return a + b

    server.register_method("add", add_handler)

    # Missing parameter
    request = JsonRpcRequest(method="add", params={"a": 5}, id="req-001", meta=None)
    response = server.handle_request(request)
    assert response is not None

    assert response.error is not None
    assert response.error.code == INVALID_PARAMS


def test_a2a_server_internal_error() -> None:
    """Test that exceptions in handlers return internal error."""
    server = A2AServer()

    def failing_handler() -> None:
        raise RuntimeError("Something went wrong")

    server.register_method("fail", failing_handler)

    request = JsonRpcRequest(method="fail", params=None, id="req-001", meta=None)
    response = server.handle_request(request)
    assert response is not None

    assert response.error is not None
    assert response.error.code == INTERNAL_ERROR
    assert "Something went wrong" in response.error.message


def test_a2a_server_with_dict_params() -> None:
    """Test method invocation with dict params."""
    server = A2AServer()

    def greet_handler(name: str, title: str = "Mr.") -> str:
        return f"Hello, {title} {name}"

    server.register_method("greet", greet_handler)

    request = JsonRpcRequest(
        method="greet", params={"name": "Smith", "title": "Dr."}, id="req-001", meta=None
    )
    response = server.handle_request(request)
    assert response is not None

    assert response.result == "Hello, Dr. Smith"


def test_a2a_server_with_list_params() -> None:
    """Test method invocation with list params."""
    server = A2AServer()

    def add_handler(a: int, b: int) -> int:
        return a + b

    server.register_method("add", add_handler)

    request = JsonRpcRequest(method="add", params=[5, 3], id="req-001", meta=None)
    response = server.handle_request(request)
    assert response is not None

    assert response.result == 8


def test_a2a_server_no_params() -> None:
    """Test method invocation with no params."""
    server = A2AServer()

    def status_handler() -> dict[str, str]:
        return {"status": "ok"}

    server.register_method("status", status_handler)

    request = JsonRpcRequest(method="status", params=None, id="req-001", meta=None)
    response = server.handle_request(request)

    assert response is not None
    assert response.result == {"status": "ok"}


def test_a2a_server_notification_success() -> None:
    """Test that successful notifications return None (no response)."""
    server = A2AServer()

    invoked = False

    def notification_handler(message: str) -> None:
        nonlocal invoked
        invoked = True

    server.register_method("notify", notification_handler)

    # Create notification (id=None)
    notification = JsonRpcRequest(method="notify", params={"message": "test"}, id=None, meta=None)
    response = server.handle_request(notification)

    # Notifications must not generate a response
    assert response is None
    assert invoked is True  # But the handler should still be invoked


def test_a2a_server_notification_method_not_found() -> None:
    """Test that notifications for non-existent methods return None."""
    server = A2AServer()

    notification = JsonRpcRequest(method="unknown", params={}, id=None, meta=None)
    response = server.handle_request(notification)

    # Notifications must not generate a response, even for errors
    assert response is None


def test_a2a_server_notification_with_error() -> None:
    """Test that notifications with errors return None (no error response)."""
    server = A2AServer()

    def failing_handler() -> None:
        raise RuntimeError("Error in notification handler")

    server.register_method("fail", failing_handler)

    notification = JsonRpcRequest(method="fail", params=None, id=None, meta=None)
    response = server.handle_request(notification)

    # Notifications must not generate a response, even when handler fails
    assert response is None


def test_a2a_server_notification_invalid_params() -> None:
    """Test that notifications with invalid params return None."""
    server = A2AServer()

    def handler(required_param: str) -> None:
        pass

    server.register_method("test", handler)

    # Missing required parameter
    notification = JsonRpcRequest(method="test", params={}, id=None, meta=None)
    response = server.handle_request(notification)

    # Notifications must not generate a response, even for parameter errors
    assert response is None


def test_a2a_client_create_request() -> None:
    """Test creating requests with A2A client."""
    client = A2AClient()

    request = client.create_request("echo", {"message": "hello"})

    assert request.method == "echo"
    assert request.params == {"message": "hello"}
    assert request.id is not None  # Auto-generated


def test_a2a_client_create_notification() -> None:
    """Test creating notifications with A2A client."""
    client = A2AClient()

    notification = client.create_notification("notify", {"event": "started"})

    assert notification.method == "notify"
    assert notification.id is None  # Notifications have no ID


def test_a2a_client_parse_response() -> None:
    """Test parsing response data."""
    client = A2AClient()

    response_data = {
        "jsonrpc": "2.0",
        "id": "req-001",
        "result": {"echo": "hello"},
    }

    response = client.parse_response(response_data)

    assert response.id == "req-001"
    assert response.result == {"echo": "hello"}


# ============================================================================
# Integration Tests
# ============================================================================


def test_full_a2a_workflow() -> None:
    """Test complete A2A workflow: discovery + communication."""
    # Setup discovery
    discovery = DiscoveryClient(InMemoryDiscovery())

    # Register agent
    card = (
        AgentCardBuilder("data-processor", "Data Processor", "1.0.0")
        .add_capability("process_data", description="Process data inputs")
        .add_endpoint("http", "http://localhost:8080/rpc")
        .with_metadata(tags=["data", "processing"])
        .build()
    )
    discovery.register(card)

    # Find agent by capability
    agents = discovery.find_agents_by_capability("process_data")
    assert len(agents) == 1

    # Setup server for the agent
    server = A2AServer()

    def process_data_handler(data: list[int]) -> dict[str, Any]:
        return {"sum": sum(data), "count": len(data)}

    server.register_method("process_data", process_data_handler)

    # Create client request
    client = A2AClient()
    request = client.create_request("process_data", {"data": [1, 2, 3, 4, 5]})

    # Server handles request
    response = server.handle_request(request)

    # Verify response
    assert response is not None
    assert response.error is None
    assert response.result == {"sum": 15, "count": 5}


def test_jsonrpc_compliance() -> None:
    """Test JSON-RPC 2.0 compliance in request/response cycle."""
    server = A2AServer()

    def calculator_add(a: int, b: int) -> int:
        return a + b

    server.register_method("add", calculator_add)

    # Test 1: Standard request with dict params
    request1 = JsonRpcRequest(method="add", params={"a": 10, "b": 20}, id=1, meta=None)
    response1 = server.handle_request(request1)
    assert response1 is not None

    assert response1.jsonrpc == "2.0"
    assert response1.id == 1
    assert response1.result == 30
    assert response1.error is None

    # Test 2: Request with list params
    request2 = JsonRpcRequest(method="add", params=[15, 25], id=2, meta=None)
    response2 = server.handle_request(request2)
    assert response2 is not None

    assert response2.jsonrpc == "2.0"
    assert response2.id == 2
    assert response2.result == 40

    # Test 3: Error response for method not found
    request3 = JsonRpcRequest(method="subtract", params=[10, 5], id=3, meta=None)
    response3 = server.handle_request(request3)
    assert response3 is not None

    assert response3.jsonrpc == "2.0"
    assert response3.id == 3
    assert response3.result is None
    assert response3.error is not None
    assert response3.error.code == METHOD_NOT_FOUND
