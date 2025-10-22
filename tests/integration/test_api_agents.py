"""Integration tests for /agents API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agdd.api.server import app

client = TestClient(app)


def test_health_check() -> None:
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_agents() -> None:
    """Test listing registered agents."""
    response = client.get("/api/v1/agents")
    assert response.status_code == 200
    agents = response.json()
    assert isinstance(agents, list)
    # Should have at least the offer-orchestrator-mag from registry
    assert any(agent["slug"] == "offer-orchestrator-mag" for agent in agents)


def test_list_agents_has_required_fields() -> None:
    """Test agent list response schema."""
    response = client.get("/api/v1/agents")
    assert response.status_code == 200
    agents = response.json()

    if agents:
        agent = agents[0]
        assert "slug" in agent
        assert isinstance(agent["slug"], str)
        # title and description are optional


def test_run_agent_not_found() -> None:
    """Test running non-existent agent returns 404."""
    response = client.post(
        "/api/v1/agents/nonexistent-agent/run",
        json={"payload": {"foo": "bar"}},
    )
    assert response.status_code == 404
    error = response.json()
    assert "detail" in error
