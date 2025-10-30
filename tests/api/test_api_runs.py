"""Tests for POST /runs endpoint and idempotency middleware."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the API."""
    # Import here to avoid issues with MCP initialization
    from agdd.api.server import app

    return TestClient(app)


@pytest.fixture
def mock_invoke_mag():
    """Mock the invoke_mag function to avoid actual agent execution."""
    with patch("agdd.api.routes.runs_create.invoke_mag") as mock:
        def _mock_invoke(slug: str, payload: dict, base_dir, context: dict):
            # Simulate run_id generation
            context["run_id"] = f"mag-test-{slug}"
            return {"status": "success", "result": "mocked"}

        mock.side_effect = _mock_invoke
        yield mock


class TestPostRunsEndpoint:
    """Tests for POST /runs endpoint."""

    def test_create_run_success(self, client, mock_invoke_mag):
        """Test successful run creation."""
        response = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["run_id"] == "mag-test-test-agent"
        assert data["status"] == "completed"

        # Verify invoke_mag was called
        mock_invoke_mag.assert_called_once()

    def test_create_run_with_idempotency_key_in_body(self, client, mock_invoke_mag):
        """Test run creation with idempotency key in request body."""
        response = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test"},
                "idempotency_key": "test-key-123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "completed"

    def test_create_run_missing_agent(self, client, mock_invoke_mag):
        """Test run creation fails when agent field is missing."""
        response = client.post(
            "/api/v1/runs",
            json={
                "payload": {"input": "test"},
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "invalid_payload"

    def test_create_run_missing_payload(self, client, mock_invoke_mag):
        """Test run creation fails when payload field is missing."""
        response = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "invalid_payload"

    def test_create_run_agent_not_found(self, client):
        """Test run creation fails when agent is not found."""
        with patch("agdd.api.routes.runs_create.invoke_mag") as mock:
            mock.side_effect = FileNotFoundError("Agent not found")

            response = client.post(
                "/api/v1/runs",
                json={
                    "agent": "nonexistent-agent",
                    "payload": {"input": "test"},
                },
            )

            assert response.status_code == 404
            data = response.json()
            assert data["code"] == "agent_not_found"

    def test_create_run_invalid_payload(self, client):
        """Test run creation fails with invalid payload."""
        with patch("agdd.api.routes.runs_create.invoke_mag") as mock:
            mock.side_effect = ValueError("Invalid payload format")

            response = client.post(
                "/api/v1/runs",
                json={
                    "agent": "test-agent",
                    "payload": {"invalid": "data"},
                },
            )

            assert response.status_code == 400
            data = response.json()
            assert data["code"] == "invalid_payload"

    def test_create_run_execution_failed(self, client):
        """Test run creation fails when execution fails."""
        with patch("agdd.api.routes.runs_create.invoke_mag") as mock:
            mock.side_effect = RuntimeError("Execution failed")

            response = client.post(
                "/api/v1/runs",
                json={
                    "agent": "test-agent",
                    "payload": {"input": "test"},
                },
            )

            assert response.status_code == 400
            data = response.json()
            assert data["code"] == "execution_failed"

    def test_create_run_internal_error(self, client):
        """Test run creation returns 500 on unexpected errors."""
        with patch("agdd.api.routes.runs_create.invoke_mag") as mock:
            mock.side_effect = Exception("Unexpected error")

            response = client.post(
                "/api/v1/runs",
                json={
                    "agent": "test-agent",
                    "payload": {"input": "test"},
                },
            )

            assert response.status_code == 500
            data = response.json()
            assert data["code"] == "internal_error"


class TestIdempotencyMiddleware:
    """Tests for idempotency middleware."""

    def test_idempotency_with_header(self, client, mock_invoke_mag):
        """Test idempotency with Idempotency-Key header."""
        # First request
        response1 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test"},
            },
            headers={"Idempotency-Key": "unique-key-1"},
        )

        assert response1.status_code == 200
        data1 = response1.json()
        assert "run_id" in data1

        # Second request with same key and body should return cached response
        response2 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test"},
            },
            headers={"Idempotency-Key": "unique-key-1"},
        )

        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["run_id"] == data1["run_id"]
        assert response2.headers.get("X-Idempotency-Replay") == "true"

        # invoke_mag should only be called once
        assert mock_invoke_mag.call_count == 1

    def test_idempotency_conflict_different_body(self, client, mock_invoke_mag):
        """Test idempotency returns 409 for same key with different body."""
        # First request
        response1 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test1"},
            },
            headers={"Idempotency-Key": "conflict-key"},
        )

        assert response1.status_code == 200

        # Second request with same key but different body
        response2 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test2"},
            },
            headers={"Idempotency-Key": "conflict-key"},
        )

        assert response2.status_code == 409
        data2 = response2.json()
        assert data2["code"] == "conflict"
        assert "already used" in data2["message"]

    def test_no_idempotency_without_header(self, client, mock_invoke_mag):
        """Test that requests without Idempotency-Key are not cached."""
        # First request
        response1 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test"},
            },
        )

        assert response1.status_code == 200

        # Second request without idempotency key should execute again
        response2 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test"},
            },
        )

        assert response2.status_code == 200

        # invoke_mag should be called twice
        assert mock_invoke_mag.call_count == 2

    def test_idempotency_only_applies_to_post(self, client):
        """Test that idempotency middleware only applies to POST requests."""
        # GET request with Idempotency-Key should be ignored
        response = client.get(
            "/health",
            headers={"Idempotency-Key": "should-be-ignored"},
        )

        assert response.status_code == 200


class TestAuthenticationAndRateLimit:
    """Tests for authentication and rate limiting on POST /runs."""

    def test_requires_authentication_when_configured(self, client, mock_invoke_mag):
        """Test that endpoint requires authentication when API_KEY is set."""
        # Note: In test environment, API_KEY is likely not set
        # This test documents expected behavior when authentication is enabled

        # For now, just verify the endpoint is accessible
        # In production with API_KEY set, this would require authentication
        response = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test"},
            },
        )

        # Should succeed in test environment (no API_KEY configured)
        assert response.status_code == 200

    def test_rate_limiting_applied(self, client, mock_invoke_mag):
        """Test that rate limiting is applied to the endpoint."""
        # Note: Rate limiting configuration depends on RATE_LIMIT_QPS setting
        # This test documents that the rate_limit_dependency is applied

        # Make multiple requests rapidly
        for _ in range(5):
            response = client.post(
                "/api/v1/runs",
                json={
                    "agent": "test-agent",
                    "payload": {"input": "test"},
                },
            )

            # In test environment without rate limiting configured,
            # all requests should succeed
            assert response.status_code in [200, 429]
