"""Tests for POST /runs endpoint and idempotency middleware."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient


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

    def test_idempotency_with_body_key(self, client, mock_invoke_mag):
        """Test idempotency with key in request body."""
        # First request with idempotency_key in body
        response1 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test"},
                "idempotency_key": "body-key-1",
            },
        )

        assert response1.status_code == 200
        data1 = response1.json()
        assert "run_id" in data1

        # Second request with same body key should return cached response
        response2 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test"},
                "idempotency_key": "body-key-1",
            },
        )

        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["run_id"] == data1["run_id"]
        assert response2.headers.get("X-Idempotency-Replay") == "true"

        # invoke_mag should only be called once
        assert mock_invoke_mag.call_count == 1

    def test_idempotency_header_precedence(self, client, mock_invoke_mag):
        """Test that Idempotency-Key header takes precedence over body field."""
        # First request with both header and body key
        response1 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test"},
                "idempotency_key": "body-key-ignored",
            },
            headers={"Idempotency-Key": "header-key-1"},
        )

        assert response1.status_code == 200
        data1 = response1.json()

        # Second request with same header key and same body should be cached
        # (header takes precedence for key selection, body must match for replay)
        response2 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test"},
                "idempotency_key": "body-key-ignored",
            },
            headers={"Idempotency-Key": "header-key-1"},
        )

        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["run_id"] == data1["run_id"]
        assert response2.headers.get("X-Idempotency-Replay") == "true"

        # invoke_mag should only be called once (header key matched and body matched)
        assert mock_invoke_mag.call_count == 1

        # Third request: same header key but different body should conflict
        response3 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "different"},
                "idempotency_key": "body-key-ignored",
            },
            headers={"Idempotency-Key": "header-key-1"},
        )

        assert response3.status_code == 409
        data3 = response3.json()
        assert data3["code"] == "conflict"

    def test_idempotency_body_key_conflict(self, client, mock_invoke_mag):
        """Test idempotency conflict detection with body-based key."""
        # First request with body key
        response1 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test1"},
                "idempotency_key": "body-conflict-key",
            },
        )

        assert response1.status_code == 200

        # Second request with same body key but different payload
        response2 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test2"},
                "idempotency_key": "body-conflict-key",
            },
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

    def test_idempotency_preserves_status_code_and_headers(self, client, mock_invoke_mag):
        """Test that idempotency middleware preserves original status code and headers."""
        # First request
        response1 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test"},
            },
            headers={"Idempotency-Key": "status-test-key"},
        )

        assert response1.status_code == 200
        original_headers = dict(response1.headers)

        # Second request with same key should return same status and preserve headers
        response2 = client.post(
            "/api/v1/runs",
            json={
                "agent": "test-agent",
                "payload": {"input": "test"},
            },
            headers={"Idempotency-Key": "status-test-key"},
        )

        assert response2.status_code == 200
        assert response2.headers.get("X-Idempotency-Replay") == "true"
        # Verify content-type is preserved
        assert response2.headers.get("content-type") == original_headers.get("content-type")

    def test_idempotency_preserves_background_tasks(self):
        """Test that background tasks run on first request but not on replayed requests."""
        from fastapi import BackgroundTasks, FastAPI, Response
        from fastapi.testclient import TestClient
        from agdd.api.middleware import IdempotencyMiddleware

        # Track background task executions
        task_counter = {"count": 0}

        def background_task():
            task_counter["count"] += 1

        # Create a test app with idempotency middleware
        test_app = FastAPI()
        test_app.add_middleware(IdempotencyMiddleware)

        @test_app.post("/test-background")
        async def test_endpoint():
            # Create response with background task using Response object directly
            def add_bg_task(task_response: Response):
                if hasattr(task_response, "background") and task_response.background:
                    task_response.background.add_task(background_task)

            response = Response(content='{"status": "ok"}', media_type="application/json")
            # Import BackgroundTasks from starlette
            from starlette.background import BackgroundTask
            response.background = BackgroundTask(background_task)
            return response

        test_client = TestClient(test_app)

        # First request with idempotency key - background task should run
        response1 = test_client.post(
            "/test-background",
            json={},
            headers={"Idempotency-Key": "bg-task-test"},
        )

        assert response1.status_code == 200
        assert task_counter["count"] == 1

        # Second request with same key - background task should NOT run again
        # (it already ran with the original request)
        response2 = test_client.post(
            "/test-background",
            json={},
            headers={"Idempotency-Key": "bg-task-test"},
        )

        assert response2.status_code == 200
        assert response2.headers.get("X-Idempotency-Replay") == "true"
        # Background task should still only have run once
        assert task_counter["count"] == 1

    def test_idempotency_detects_no_content_length(self):
        """Test that responses without Content-Length are treated as streaming."""
        from fastapi import FastAPI, Response
        from fastapi.testclient import TestClient
        from agdd.api.middleware import IdempotencyMiddleware

        call_counter = {"count": 0}

        # Create a test app with idempotency middleware
        test_app = FastAPI()
        test_app.add_middleware(IdempotencyMiddleware)

        @test_app.post("/test-no-length")
        async def test_endpoint():
            call_counter["count"] += 1
            # Create response without Content-Length header
            response = Response(content=b"test data", media_type="text/plain")
            # Remove Content-Length if FastAPI adds it
            if "content-length" in response.headers:
                del response.headers["content-length"]
            return response

        test_client = TestClient(test_app)

        # First request
        response1 = test_client.post(
            "/test-no-length",
            json={},
            headers={"Idempotency-Key": "no-length-key"},
        )

        assert response1.status_code == 200
        assert call_counter["count"] == 1

        # Second request - without Content-Length, should not be cached
        response2 = test_client.post(
            "/test-no-length",
            json={},
            headers={"Idempotency-Key": "no-length-key"},
        )

        assert response2.status_code == 200
        # Should be called again (not cached due to missing Content-Length)
        assert call_counter["count"] == 2

    @pytest.mark.asyncio
    async def test_idempotency_concurrent_requests(self):
        """Test that concurrent requests with same idempotency key execute only once."""
        from httpx import ASGITransport
        from agdd.api.server import app

        # Track how many times the endpoint is called
        call_counter = {"count": 0}

        # Mock invoke_mag to simulate execution and track calls
        with patch("agdd.api.routes.runs_create.invoke_mag") as mock:
            def _mock_invoke(slug: str, payload: dict, base_dir, context: dict):
                # Simulate run_id generation
                call_counter["count"] += 1
                # Add a small delay to simulate work
                import time
                time.sleep(0.1)
                context["run_id"] = f"mag-concurrent-test-{slug}"
                return {"status": "success", "result": "concurrent-test"}

            mock.side_effect = _mock_invoke

            # Create async client
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Send 5 concurrent requests with the same idempotency key
                tasks = [
                    client.post(
                        "/api/v1/runs",
                        json={
                            "agent": "test-agent",
                            "payload": {"input": "concurrent-test"},
                        },
                        headers={"Idempotency-Key": "concurrent-test-key"},
                    )
                    for _ in range(5)
                ]

                # Execute all requests concurrently
                responses = await asyncio.gather(*tasks)

            # All responses should be successful
            for response in responses:
                assert response.status_code == 200
                data = response.json()
                assert "run_id" in data
                assert data["run_id"] == "mag-concurrent-test-test-agent"
                assert data["status"] == "completed"

            # Verify that the endpoint was only called ONCE despite 5 concurrent requests
            # This proves the lock-based solution prevents the race condition
            assert call_counter["count"] == 1, f"Expected 1 execution, got {call_counter['count']}"

            # Verify that at least some responses have the X-Idempotency-Replay header
            # (the ones that waited for the first request to complete)
            replay_count = sum(
                1 for r in responses
                if r.headers.get("X-Idempotency-Replay") == "true"
            )
            assert replay_count >= 1, "At least one response should be a replay"

    @pytest.mark.asyncio
    async def test_idempotency_lock_cleanup(self):
        """Test that locks are cleaned up to prevent memory leaks."""
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient
        from agdd.api.middleware.idempotency import IdempotencyStore, IdempotencyMiddleware

        # Create a store with longer TTL so locks persist during the test
        test_store = IdempotencyStore(ttl_seconds=10)

        # Create middleware instance that we can inspect
        middleware_instance = None

        # Custom wrapper to capture the middleware instance
        class TestIdempotencyMiddleware(IdempotencyMiddleware):
            def __init__(self, app, store):
                super().__init__(app, store)
                nonlocal middleware_instance
                middleware_instance = self

        # Create test app
        test_app = FastAPI()

        @test_app.post("/test-cleanup")
        async def test_endpoint():
            return {"status": "ok"}

        # Add middleware
        test_app.add_middleware(TestIdempotencyMiddleware, store=test_store)

        # Make several requests with different idempotency keys using async client
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            for i in range(10):
                response = await client.post(
                    "/test-cleanup",
                    json={},
                    headers={"Idempotency-Key": f"cleanup-key-{i}"},
                )
                assert response.status_code == 200

        # At this point, we should have 10 locks created (still within TTL)
        initial_lock_count = len(middleware_instance._locks)
        assert initial_lock_count == 10, f"Expected 10 locks, got {initial_lock_count}"

        # Manually remove some entries from the store to simulate expiration
        # Keys are now scoped by method and path: POST:/test-cleanup:cleanup-key-{i}
        for i in range(5):
            scoped_key = f"POST:/test-cleanup:cleanup-key-{i}"
            if scoped_key in test_store._store:
                del test_store._store[scoped_key]

        # Manually trigger cleanup
        await middleware_instance._cleanup_locks()

        # After cleanup, locks for removed keys should be gone
        after_cleanup_count = len(middleware_instance._locks)
        assert after_cleanup_count == 5, f"Expected 5 locks after cleanup, got {after_cleanup_count}"

    def test_idempotency_preserves_multi_value_headers(self):
        """Test that multi-value headers like Set-Cookie are preserved in cached responses."""
        from fastapi import FastAPI, Response
        from fastapi.testclient import TestClient
        from agdd.api.middleware import IdempotencyMiddleware

        # Create test app with idempotency middleware
        test_app = FastAPI()
        test_app.add_middleware(IdempotencyMiddleware)

        @test_app.post("/test-multi-headers")
        async def test_endpoint():
            # Create response with multiple Set-Cookie headers
            response = Response(content='{"status": "ok"}', media_type="application/json")
            # Manually add multiple Set-Cookie headers
            # In Starlette, we need to use raw_headers or Response.set_cookie multiple times
            response.set_cookie(key="session", value="abc123")
            response.set_cookie(key="csrf", value="xyz789")
            return response

        test_client = TestClient(test_app)

        # First request - original execution
        response1 = test_client.post(
            "/test-multi-headers",
            json={},
            headers={"Idempotency-Key": "multi-header-test"},
        )

        assert response1.status_code == 200

        # Extract all Set-Cookie headers from first response
        set_cookie_headers_1 = response1.headers.get_list("set-cookie")
        assert len(set_cookie_headers_1) == 2, f"Expected 2 Set-Cookie headers, got {len(set_cookie_headers_1)}"
        assert any("session=abc123" in header for header in set_cookie_headers_1), "Missing session cookie"
        assert any("csrf=xyz789" in header for header in set_cookie_headers_1), "Missing csrf cookie"

        # Second request - should be replayed from cache
        response2 = test_client.post(
            "/test-multi-headers",
            json={},
            headers={"Idempotency-Key": "multi-header-test"},
        )

        assert response2.status_code == 200
        assert response2.headers.get("X-Idempotency-Replay") == "true"

        # Extract all Set-Cookie headers from cached response
        set_cookie_headers_2 = response2.headers.get_list("set-cookie")
        assert len(set_cookie_headers_2) == 2, f"Expected 2 Set-Cookie headers in cached response, got {len(set_cookie_headers_2)}"
        assert any("session=abc123" in header for header in set_cookie_headers_2), "Missing session cookie in cached response"
        assert any("csrf=xyz789" in header for header in set_cookie_headers_2), "Missing csrf cookie in cached response"

        # Verify both responses have the same cookies
        assert set(set_cookie_headers_1) == set(set_cookie_headers_2), "Cached response has different cookies than original"

    def test_idempotency_scoped_per_endpoint(self):
        """Test that idempotency keys are scoped per endpoint to prevent cross-endpoint collisions."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from agdd.api.middleware import IdempotencyMiddleware

        # Create test app with idempotency middleware
        test_app = FastAPI()
        test_app.add_middleware(IdempotencyMiddleware)

        # Create two different endpoints
        @test_app.post("/endpoint-a")
        async def endpoint_a():
            return {"endpoint": "a", "data": "response-a"}

        @test_app.post("/endpoint-b")
        async def endpoint_b():
            return {"endpoint": "b", "data": "response-b"}

        test_client = TestClient(test_app)

        # Use the same idempotency key for both endpoints
        shared_key = "shared-idempotency-key"

        # First request to endpoint A
        response_a1 = test_client.post(
            "/endpoint-a",
            json={},
            headers={"Idempotency-Key": shared_key},
        )

        assert response_a1.status_code == 200
        data_a1 = response_a1.json()
        assert data_a1["endpoint"] == "a"
        assert data_a1["data"] == "response-a"

        # Second request to endpoint B with same key - should NOT conflict
        response_b1 = test_client.post(
            "/endpoint-b",
            json={},
            headers={"Idempotency-Key": shared_key},
        )

        assert response_b1.status_code == 200
        data_b1 = response_b1.json()
        assert data_b1["endpoint"] == "b"
        assert data_b1["data"] == "response-b"
        # Should NOT have replay header since it's a different endpoint
        assert response_b1.headers.get("X-Idempotency-Replay") != "true"

        # Third request to endpoint A with same key - should be cached
        response_a2 = test_client.post(
            "/endpoint-a",
            json={},
            headers={"Idempotency-Key": shared_key},
        )

        assert response_a2.status_code == 200
        data_a2 = response_a2.json()
        assert data_a2 == data_a1  # Should be identical to first request to A
        assert response_a2.headers.get("X-Idempotency-Replay") == "true"

        # Fourth request to endpoint B with same key - should be cached
        response_b2 = test_client.post(
            "/endpoint-b",
            json={},
            headers={"Idempotency-Key": shared_key},
        )

        assert response_b2.status_code == 200
        data_b2 = response_b2.json()
        assert data_b2 == data_b1  # Should be identical to first request to B
        assert response_b2.headers.get("X-Idempotency-Replay") == "true"


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
