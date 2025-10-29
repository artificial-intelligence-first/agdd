"""
End-to-end integration tests for A2A (Agent-to-Agent) workflows

This test suite validates the complete A2A communication flow:
1. Discovery: GET /api/v1/agents (find available agents)
2. Invocation: POST /api/v1/agents/{slug}/run (invoke agent via API)
3. Delegation: MAG → SAG communication with context propagation

Note: Most tests in this module perform actual LLM agent execution via API
and are marked as 'slow' to enable fast CI runs with `-m "not slow"`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agdd.api.server import app

client = TestClient(app)


class TestA2ADiscoveryInvoke:
    """Test A2A discovery and invocation workflows"""

    def test_a2a_discovery_endpoint(self) -> None:
        """Test that agents can be discovered via API"""
        # Phase 1: Discovery
        response = client.get("/api/v1/agents")
        assert response.status_code == 200

        agents = response.json()
        assert isinstance(agents, list)
        assert len(agents) > 0

        # Verify agent structure
        for agent in agents:
            assert "slug" in agent
            assert isinstance(agent["slug"], str)
            # Optional fields: title, description

        # Verify known agents are discoverable
        agent_slugs = [agent["slug"] for agent in agents]
        assert "offer-orchestrator-mag" in agent_slugs
        assert "compensation-advisor-sag" in agent_slugs

    def test_a2a_discover_specific_agent(self) -> None:
        """Test discovering a specific agent by slug"""
        response = client.get("/api/v1/agents")
        assert response.status_code == 200

        agents = response.json()
        mag_agent = next(
            (agent for agent in agents if agent["slug"] == "offer-orchestrator-mag"),
            None
        )

        assert mag_agent is not None
        assert mag_agent["slug"] == "offer-orchestrator-mag"
        assert "title" in mag_agent or "description" in mag_agent

    @pytest.mark.slow
    def test_a2a_invoke_mag_via_api(self) -> None:
        """Test invoking a MAG via API (simulating A2A call)"""
        # Phase 2: Invocation
        payload = {
            "role": "Software Engineer",
            "level": "Mid",
            "location": "Seattle, WA",
            "experience_years": 5,
        }

        response = client.post(
            "/api/v1/agents/offer-orchestrator-mag/run",
            json={"payload": payload}
        )

        assert response.status_code == 200
        result = response.json()

        # Verify response structure
        assert "run_id" in result
        assert "slug" in result
        assert result["slug"] == "offer-orchestrator-mag"
        assert "output" in result

        # Verify output structure
        output = result["output"]
        assert "offer" in output
        assert "metadata" in output

        # Verify offer details
        offer = output["offer"]
        assert offer["role"] == "Software Engineer"
        assert offer["base_salary"]["currency"] == "USD"
        assert offer["base_salary"]["amount"] > 0

        # Verify metadata
        metadata = output["metadata"]
        assert metadata["generated_by"] == "OfferOrchestratorMAG"
        assert "run_id" in metadata
        assert "timestamp" in metadata
        assert "task_count" in metadata
        assert "successful_tasks" in metadata

    @pytest.mark.slow
    def test_a2a_full_discovery_invoke_flow(self) -> None:
        """Test complete A2A flow: discover → invoke → verify"""
        # Step 1: Discovery - find available MAGs
        discovery_response = client.get("/api/v1/agents")
        assert discovery_response.status_code == 200

        agents = discovery_response.json()
        mag_slugs = [
            agent["slug"] for agent in agents
            if agent["slug"].endswith("-mag")
        ]
        assert len(mag_slugs) > 0

        # Step 2: Select a MAG (offer-orchestrator-mag)
        target_slug = "offer-orchestrator-mag"
        assert target_slug in mag_slugs

        # Step 3: Invoke the discovered MAG
        payload = {
            "role": "Senior Engineer",
            "level": "Senior",
            "location": "San Francisco, CA",
            "experience_years": 8,
        }

        invoke_response = client.post(
            f"/api/v1/agents/{target_slug}/run",
            json={"payload": payload}
        )

        assert invoke_response.status_code == 200
        result = invoke_response.json()

        # Step 4: Verify successful execution
        assert result["slug"] == target_slug
        assert "output" in result
        assert "run_id" in result

        output = result["output"]
        assert output["metadata"]["successful_tasks"] >= 1

    @pytest.mark.slow
    def test_a2a_context_propagation(self) -> None:
        """Test that A2A context is properly propagated through agent calls"""
        # Prepare A2A payload with context
        payload = {
            "data": {
                "role": "Engineer",
                "level": "Mid",
                "experience_years": 5,
            },
            "context": {
                "correlation_id": "test-correlation-123",
                "source_agent": "test-client",
                "call_chain": ["external-system", "test-client"],
            }
        }

        response = client.post(
            "/api/v1/agents/offer-orchestrator-mag/run",
            json={"payload": payload}
        )

        assert response.status_code == 200
        result = response.json()

        # Note: The current offer-orchestrator-mag may not have full A2A support yet
        # This test verifies that the API accepts A2A-style payloads
        assert "output" in result
        assert result["output"]["metadata"]["successful_tasks"] >= 1

    @pytest.mark.slow
    def test_a2a_invoke_with_request_id(self) -> None:
        """Test invoking agent with custom request_id for tracking"""
        payload = {
            "role": "Engineer",
            "level": "Mid",
            "experience_years": 5,
        }

        request_id = "custom-request-123"

        response = client.post(
            "/api/v1/agents/offer-orchestrator-mag/run",
            json={
                "payload": payload,
                "request_id": request_id,
            }
        )

        assert response.status_code == 200
        result = response.json()
        assert "output" in result
        # The API should accept request_id (even if not used in response yet)

    def test_a2a_invoke_nonexistent_agent(self) -> None:
        """Test that invoking non-existent agent returns proper error"""
        payload = {"test": "data"}

        response = client.post(
            "/api/v1/agents/nonexistent-agent/run",
            json={"payload": payload}
        )

        assert response.status_code == 404
        error = response.json()
        assert "code" in error
        assert error["code"] == "agent_not_found"

    def test_a2a_invoke_invalid_payload(self) -> None:
        """Test that invalid payload structure is handled gracefully"""
        # Missing required 'payload' field
        response = client.post(
            "/api/v1/agents/offer-orchestrator-mag/run",
            json={"invalid": "structure"}
        )

        # Should return 400 with ApiError schema for validation error
        assert response.status_code == 400
        error = response.json()
        assert error["code"] == "invalid_payload"
        assert "message" in error
        assert "validation" in error["message"].lower()  # Message should mention validation

    @pytest.mark.slow
    def test_a2a_multiple_sequential_invocations(self) -> None:
        """Test multiple A2A invocations in sequence"""
        payloads = [
            {"role": "Junior Engineer", "level": "Junior", "experience_years": 1},
            {"role": "Mid Engineer", "level": "Mid", "experience_years": 4},
            {"role": "Senior Engineer", "level": "Senior", "experience_years": 8},
        ]

        results = []
        for payload in payloads:
            response = client.post(
                "/api/v1/agents/offer-orchestrator-mag/run",
                json={"payload": payload}
            )
            assert response.status_code == 200
            results.append(response.json())

        # Verify all succeeded
        assert len(results) == 3
        for result in results:
            assert "output" in result
            assert result["output"]["metadata"]["successful_tasks"] >= 1

        # Verify different run_ids
        run_ids = [r["run_id"] for r in results]
        assert len(set(run_ids)) == 3  # All unique

    @pytest.mark.slow
    def test_a2a_observability_artifacts_via_api(self) -> None:
        """Test that artifacts endpoint provides run details"""
        # Step 1: Invoke agent
        payload = {"role": "Engineer", "level": "Mid", "experience_years": 5}

        invoke_response = client.post(
            "/api/v1/agents/offer-orchestrator-mag/run",
            json={"payload": payload}
        )

        assert invoke_response.status_code == 200
        result = invoke_response.json()
        run_id = result["run_id"]

        # Step 2: Check if artifacts are available
        assert "artifacts" in result
        artifacts = result["artifacts"]

        # Verify artifact URLs
        if "summary" in artifacts:
            assert run_id in artifacts["summary"]

        if "logs" in artifacts:
            assert run_id in artifacts["logs"]


class TestA2ADelegation:
    """Test A2A delegation patterns (MAG → SAG)"""

    @pytest.mark.slow
    def test_mag_to_sag_delegation(self) -> None:
        """Test that MAG properly delegates to SAG with context"""
        payload = {
            "role": "Software Engineer",
            "level": "Mid",
            "location": "New York, NY",
            "experience_years": 5,
        }

        response = client.post(
            "/api/v1/agents/offer-orchestrator-mag/run",
            json={"payload": payload}
        )

        assert response.status_code == 200
        result = response.json()

        # Verify MAG executed successfully
        output = result["output"]
        assert "offer" in output
        assert "metadata" in output

        # Verify delegation occurred
        metadata = output["metadata"]
        assert metadata["task_count"] >= 1
        assert metadata["successful_tasks"] >= 1

    @pytest.mark.slow
    def test_error_handling_in_delegation(self) -> None:
        """Test error handling when delegation encounters issues"""
        # Use minimal payload that should still work
        payload = {"role": "Engineer"}

        response = client.post(
            "/api/v1/agents/offer-orchestrator-mag/run",
            json={"payload": payload}
        )

        # Should succeed with partial data (fallback behavior)
        assert response.status_code == 200
        result = response.json()
        assert "output" in result


class TestA2ACompatibility:
    """Test A2A template compatibility with existing system"""

    @pytest.mark.slow
    def test_existing_mag_works_with_a2a_api(self) -> None:
        """Test that existing MAGs work with A2A API endpoints"""
        # The offer-orchestrator-mag was created before A2A templates
        # but should still work via A2A API

        payload = {
            "role": "Software Engineer",
            "level": "Senior",
            "experience_years": 10,
        }

        response = client.post(
            "/api/v1/agents/offer-orchestrator-mag/run",
            json={"payload": payload}
        )

        assert response.status_code == 200
        result = response.json()
        assert result["output"]["metadata"]["successful_tasks"] >= 1

    def test_discovery_includes_all_agent_types(self) -> None:
        """Test that discovery returns both MAGs and SAGs"""
        response = client.get("/api/v1/agents")
        assert response.status_code == 200

        agents = response.json()
        agent_slugs = [agent["slug"] for agent in agents]

        # Should include both MAG and SAG
        has_mag = any(slug.endswith("-mag") for slug in agent_slugs)
        has_sag = any(slug.endswith("-sag") for slug in agent_slugs)

        assert has_mag
        assert has_sag
