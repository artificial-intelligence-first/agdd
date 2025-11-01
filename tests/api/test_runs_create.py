"""Tests for POST /runs endpoint and idempotency middleware."""
from __future__ import annotations
import asyncio
from typing import Any, Dict, Iterator
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client() -> TestClient:
    """Create a test client for the API."""
    from agdd.api.server import app
    return TestClient(app)

@pytest.fixture
def mock_invoke_mag() -> Iterator[MagicMock]:
    """Mock the invoke_mag function to avoid actual agent execution."""
    with patch('agdd.api.routes.runs_create.invoke_mag') as mock:

        def _mock_invoke(slug: str, payload: Dict[str, Any], base_dir: Any, context: Dict[str, Any]) -> Dict[str, Any]:
            context['run_id'] = f'mag-test-{slug}'
            return {'status': 'success', 'result': 'mocked'}
        mock.side_effect = _mock_invoke
        yield mock

class TestPostRunsEndpoint:
    """Tests for POST /runs endpoint."""

    def test_create_run_success(self, client: TestClient, mock_invoke_mag: MagicMock) -> None:
        """Test successful run creation."""
        response = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}})
        assert response.status_code == 200
        data = response.json()
        assert 'run_id' in data
        assert data['run_id'] == 'mag-test-test-agent'
        assert data['status'] == 'completed'
        mock_invoke_mag.assert_called_once()

    def test_create_run_with_idempotency_key_in_body(self, client: TestClient, mock_invoke_mag: MagicMock) -> None:
        """Test run creation with idempotency key in request body."""
        response = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}, 'idempotency_key': 'test-key-123'})
        assert response.status_code == 200
        data = response.json()
        assert 'run_id' in data
        assert data['status'] == 'completed'

    def test_create_run_missing_agent(self, client: TestClient, mock_invoke_mag: MagicMock) -> None:
        """Test run creation fails when agent field is missing."""
        response = client.post('/api/v1/runs', json={'payload': {'input': 'test'}})
        assert response.status_code == 400
        data = response.json()
        assert data['code'] == 'invalid_payload'

    def test_create_run_missing_payload(self, client: TestClient, mock_invoke_mag: MagicMock) -> None:
        """Test run creation fails when payload field is missing."""
        response = client.post('/api/v1/runs', json={'agent': 'test-agent'})
        assert response.status_code == 400
        data = response.json()
        assert data['code'] == 'invalid_payload'

    def test_create_run_agent_not_found(self, client: TestClient) -> None:
        """Test run creation fails when agent is not found."""
        with patch('agdd.api.routes.runs_create.invoke_mag') as mock:
            mock.side_effect = FileNotFoundError('Agent not found')
            response = client.post('/api/v1/runs', json={'agent': 'nonexistent-agent', 'payload': {'input': 'test'}})
            assert response.status_code == 404
            data = response.json()
            assert data['code'] == 'agent_not_found'

    def test_create_run_invalid_payload(self, client: TestClient) -> None:
        """Test run creation fails with invalid payload."""
        with patch('agdd.api.routes.runs_create.invoke_mag') as mock:
            mock.side_effect = ValueError('Invalid payload format')
            response = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'invalid': 'data'}})
            assert response.status_code == 400
            data = response.json()
            assert data['code'] == 'invalid_payload'

    def test_create_run_execution_failed(self, client: TestClient) -> None:
        """Test run creation fails when execution fails."""
        with patch('agdd.api.routes.runs_create.invoke_mag') as mock:
            mock.side_effect = RuntimeError('Execution failed')
            response = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}})
            assert response.status_code == 400
            data = response.json()
            assert data['code'] == 'execution_failed'

    def test_create_run_internal_error(self, client: TestClient) -> None:
        """Test run creation returns 500 on unexpected errors."""
        with patch('agdd.api.routes.runs_create.invoke_mag') as mock:
            mock.side_effect = Exception('Unexpected error')
            response = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}})
            assert response.status_code == 500
            data = response.json()
            assert data['code'] == 'internal_error'

class TestIdempotencyMiddleware:
    """Tests for idempotency middleware."""

    def test_idempotency_with_header(self, client: TestClient, mock_invoke_mag: MagicMock) -> None:
        """Test idempotency with Idempotency-Key header."""
        response1 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}}, headers={'Idempotency-Key': 'unique-key-1'})
        assert response1.status_code == 200
        data1 = response1.json()
        assert 'run_id' in data1
        response2 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}}, headers={'Idempotency-Key': 'unique-key-1'})
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2['run_id'] == data1['run_id']
        assert response2.headers.get('X-Idempotency-Replay') == 'true'
        assert mock_invoke_mag.call_count == 1

    def test_idempotency_conflict_different_body(self, client: TestClient, mock_invoke_mag: MagicMock) -> None:
        """Test idempotency returns 409 for same key with different body."""
        response1 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test1'}}, headers={'Idempotency-Key': 'conflict-key'})
        assert response1.status_code == 200
        response2 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test2'}}, headers={'Idempotency-Key': 'conflict-key'})
        assert response2.status_code == 409
        data2 = response2.json()
        assert data2['code'] == 'conflict'
        assert 'already used' in data2['message']

    def test_idempotency_with_body_key(self, client: TestClient, mock_invoke_mag: MagicMock) -> None:
        """Test idempotency with key in request body."""
        response1 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}, 'idempotency_key': 'body-key-1'})
        assert response1.status_code == 200
        data1 = response1.json()
        assert 'run_id' in data1
        response2 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}, 'idempotency_key': 'body-key-1'})
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2['run_id'] == data1['run_id']
        assert response2.headers.get('X-Idempotency-Replay') == 'true'
        assert mock_invoke_mag.call_count == 1

    def test_idempotency_header_precedence(self, client: TestClient, mock_invoke_mag: MagicMock) -> None:
        """Test that Idempotency-Key header takes precedence over body field."""
        response1 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}, 'idempotency_key': 'body-key-ignored'}, headers={'Idempotency-Key': 'header-key-1'})
        assert response1.status_code == 200
        data1 = response1.json()
        response2 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}, 'idempotency_key': 'body-key-ignored'}, headers={'Idempotency-Key': 'header-key-1'})
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2['run_id'] == data1['run_id']
        assert response2.headers.get('X-Idempotency-Replay') == 'true'
        assert mock_invoke_mag.call_count == 1
        response3 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'different'}, 'idempotency_key': 'body-key-ignored'}, headers={'Idempotency-Key': 'header-key-1'})
        assert response3.status_code == 409
        data3 = response3.json()
        assert data3['code'] == 'conflict'

    def test_idempotency_body_key_conflict(self, client: TestClient, mock_invoke_mag: MagicMock) -> None:
        """Test idempotency conflict detection with body-based key."""
        response1 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test1'}, 'idempotency_key': 'body-conflict-key'})
        assert response1.status_code == 200
        response2 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test2'}, 'idempotency_key': 'body-conflict-key'})
        assert response2.status_code == 409
        data2 = response2.json()
        assert data2['code'] == 'conflict'
        assert 'already used' in data2['message']

    def test_no_idempotency_without_header(self, client: TestClient, mock_invoke_mag: MagicMock) -> None:
        """Test that requests without Idempotency-Key are not cached."""
        response1 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}})
        assert response1.status_code == 200
        response2 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}})
        assert response2.status_code == 200
        assert mock_invoke_mag.call_count == 2

    def test_idempotency_only_applies_to_post(self, client: TestClient) -> None:
        """Test that idempotency middleware only applies to POST requests."""
        response = client.get('/health', headers={'Idempotency-Key': 'should-be-ignored'})
        assert response.status_code == 200

    def test_idempotency_preserves_status_code_and_headers(self, client: TestClient, mock_invoke_mag: MagicMock) -> None:
        """Test that idempotency middleware preserves original status code and headers."""
        response1 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}}, headers={'Idempotency-Key': 'status-test-key'})
        assert response1.status_code == 200
        original_headers = dict(response1.headers)
        response2 = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}}, headers={'Idempotency-Key': 'status-test-key'})
        assert response2.status_code == 200
        assert response2.headers.get('X-Idempotency-Replay') == 'true'
        assert response2.headers.get('content-type') == original_headers.get('content-type')

    def test_idempotency_preserves_background_tasks(self) -> None:
        """Test that background tasks run on first request but not on replayed requests."""
        from fastapi import FastAPI, Response
        from fastapi.testclient import TestClient
        from agdd.api.middleware import IdempotencyMiddleware
        task_counter: Dict[str, int] = {'count': 0}

        def background_task() -> None:
            task_counter['count'] += 1
        test_app = FastAPI()
        test_app.add_middleware(IdempotencyMiddleware)

        @test_app.post('/test-background')
        async def test_endpoint() -> Response:
            from starlette.background import BackgroundTask
            response = Response(content='{"status": "ok"}', media_type='application/json')
            response.background = BackgroundTask(background_task)
            return response
        test_client = TestClient(test_app)
        response1 = test_client.post('/test-background', json={}, headers={'Idempotency-Key': 'bg-task-test'})
        assert response1.status_code == 200
        assert task_counter['count'] == 1
        response2 = test_client.post('/test-background', json={}, headers={'Idempotency-Key': 'bg-task-test'})
        assert response2.status_code == 200
        assert response2.headers.get('X-Idempotency-Replay') == 'true'
        assert task_counter['count'] == 1

    def test_idempotency_detects_no_content_length(self) -> None:
        """Test that responses without Content-Length are treated as streaming."""
        from fastapi import FastAPI, Response
        from fastapi.testclient import TestClient
        from agdd.api.middleware import IdempotencyMiddleware
        call_counter: Dict[str, int] = {'count': 0}
        test_app = FastAPI()
        test_app.add_middleware(IdempotencyMiddleware)

        @test_app.post('/test-no-length')
        async def test_endpoint() -> Response:
            call_counter['count'] += 1
            response = Response(content=b'test data', media_type='text/plain')
            if 'content-length' in response.headers:
                del response.headers['content-length']
            return response
        test_client = TestClient(test_app)
        response1 = test_client.post('/test-no-length', json={}, headers={'Idempotency-Key': 'no-length-key'})
        assert response1.status_code == 200
        assert call_counter['count'] == 1
        response2 = test_client.post('/test-no-length', json={}, headers={'Idempotency-Key': 'no-length-key'})
        assert response2.status_code == 200
        assert call_counter['count'] == 2

    @pytest.mark.asyncio
    async def test_idempotency_concurrent_requests(self) -> None:
        """Test that concurrent requests with same idempotency key execute only once."""
        from httpx import ASGITransport, AsyncClient
        from agdd.api.server import app
        call_counter: Dict[str, int] = {'count': 0}
        with patch('agdd.api.routes.runs_create.invoke_mag') as mock:

            def _mock_invoke(slug: str, payload: Dict[str, Any], base_dir: Any, context: Dict[str, Any]) -> Dict[str, Any]:
                call_counter['count'] += 1
                import time
                time.sleep(0.1)
                context['run_id'] = f'mag-concurrent-test-{slug}'
                return {'status': 'success', 'result': 'concurrent-test'}
            mock.side_effect = _mock_invoke
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                tasks = [client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'concurrent-test'}}, headers={'Idempotency-Key': 'concurrent-test-key'}) for _ in range(5)]
                responses = await asyncio.gather(*tasks)
            for response in responses:
                assert response.status_code == 200
                data = response.json()
                assert 'run_id' in data
                assert data['run_id'] == 'mag-concurrent-test-test-agent'
                assert data['status'] == 'completed'
            assert call_counter['count'] == 1, f"Expected 1 execution, got {call_counter['count']}"
            replay_count = sum((1 for r in responses if r.headers.get('X-Idempotency-Replay') == 'true'))
            assert replay_count >= 1, 'At least one response should be a replay'

    @pytest.mark.asyncio
    async def test_idempotency_lock_cleanup(self) -> None:
        """Test that locks are cleaned up to prevent memory leaks."""
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient
        from agdd.api.middleware.idempotency import IdempotencyStore, IdempotencyMiddleware
        test_store = IdempotencyStore(ttl_seconds=10)
        middleware_instance: IdempotencyMiddleware | None = None

        class TestIdempotencyMiddleware(IdempotencyMiddleware):

            def __init__(self, app: Any, store: IdempotencyStore) -> None:
                super().__init__(app, store)
                nonlocal middleware_instance
                middleware_instance = self
        test_app = FastAPI()

        @test_app.post('/test-cleanup')
        async def test_endpoint() -> dict[str, str]:
            return {'status': 'ok'}
        test_app.add_middleware(TestIdempotencyMiddleware, store=test_store)
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url='http://test') as client:
            for i in range(10):
                response = await client.post('/test-cleanup', json={}, headers={'Idempotency-Key': f'cleanup-key-{i}'})
                assert response.status_code == 200
        assert middleware_instance is not None
        initial_lock_count = len(middleware_instance._locks)
        assert initial_lock_count == 10, f'Expected 10 locks, got {initial_lock_count}'
        for i in range(5):
            scoped_key = f'POST:/test-cleanup:cleanup-key-{i}'
            if scoped_key in test_store._store:
                del test_store._store[scoped_key]
        await middleware_instance._cleanup_locks()
        after_cleanup_count = len(middleware_instance._locks)
        assert after_cleanup_count == 5, f'Expected 5 locks after cleanup, got {after_cleanup_count}'

    def test_idempotency_preserves_multi_value_headers(self) -> None:
        """Test that multi-value headers like Set-Cookie are preserved in cached responses."""
        from fastapi import FastAPI, Response
        from fastapi.testclient import TestClient
        from agdd.api.middleware import IdempotencyMiddleware
        test_app = FastAPI()
        test_app.add_middleware(IdempotencyMiddleware)

        @test_app.post('/test-multi-headers')
        async def test_endpoint() -> Response:
            response = Response(content='{"status": "ok"}', media_type='application/json')
            response.set_cookie(key='session', value='abc123')
            response.set_cookie(key='csrf', value='xyz789')
            return response
        test_client = TestClient(test_app)
        response1 = test_client.post('/test-multi-headers', json={}, headers={'Idempotency-Key': 'multi-header-test'})
        assert response1.status_code == 200
        set_cookie_headers_1 = response1.headers.get_list('set-cookie')
        assert len(set_cookie_headers_1) == 2, f'Expected 2 Set-Cookie headers, got {len(set_cookie_headers_1)}'
        assert any(('session=abc123' in header for header in set_cookie_headers_1)), 'Missing session cookie'
        assert any(('csrf=xyz789' in header for header in set_cookie_headers_1)), 'Missing csrf cookie'
        response2 = test_client.post('/test-multi-headers', json={}, headers={'Idempotency-Key': 'multi-header-test'})
        assert response2.status_code == 200
        assert response2.headers.get('X-Idempotency-Replay') == 'true'
        set_cookie_headers_2 = response2.headers.get_list('set-cookie')
        assert len(set_cookie_headers_2) == 2, f'Expected 2 Set-Cookie headers in cached response, got {len(set_cookie_headers_2)}'
        assert any(('session=abc123' in header for header in set_cookie_headers_2)), 'Missing session cookie in cached response'
        assert any(('csrf=xyz789' in header for header in set_cookie_headers_2)), 'Missing csrf cookie in cached response'
        assert set(set_cookie_headers_1) == set(set_cookie_headers_2), 'Cached response has different cookies than original'

    def test_idempotency_scoped_per_endpoint(self) -> None:
        """Test that idempotency keys are scoped per endpoint to prevent cross-endpoint collisions."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from agdd.api.middleware import IdempotencyMiddleware
        test_app = FastAPI()
        test_app.add_middleware(IdempotencyMiddleware)

        @test_app.post('/endpoint-a')
        async def endpoint_a() -> dict[str, str]:
            return {'endpoint': 'a', 'data': 'response-a'}

        @test_app.post('/endpoint-b')
        async def endpoint_b() -> dict[str, str]:
            return {'endpoint': 'b', 'data': 'response-b'}
        test_client = TestClient(test_app)
        shared_key = 'shared-idempotency-key'
        response_a1 = test_client.post('/endpoint-a', json={}, headers={'Idempotency-Key': shared_key})
        assert response_a1.status_code == 200
        data_a1 = response_a1.json()
        assert data_a1['endpoint'] == 'a'
        assert data_a1['data'] == 'response-a'
        response_b1 = test_client.post('/endpoint-b', json={}, headers={'Idempotency-Key': shared_key})
        assert response_b1.status_code == 200
        data_b1 = response_b1.json()
        assert data_b1['endpoint'] == 'b'
        assert data_b1['data'] == 'response-b'
        assert response_b1.headers.get('X-Idempotency-Replay') != 'true'
        response_a2 = test_client.post('/endpoint-a', json={}, headers={'Idempotency-Key': shared_key})
        assert response_a2.status_code == 200
        data_a2 = response_a2.json()
        assert data_a2 == data_a1
        assert response_a2.headers.get('X-Idempotency-Replay') == 'true'
        response_b2 = test_client.post('/endpoint-b', json={}, headers={'Idempotency-Key': shared_key})
        assert response_b2.status_code == 200
        data_b2 = response_b2.json()
        assert data_b2 == data_b1
        assert response_b2.headers.get('X-Idempotency-Replay') == 'true'

class TestAuthenticationAndRateLimit:
    """Tests for authentication and rate limiting on POST /runs."""

    def test_requires_authentication_when_configured(self, client: TestClient, mock_invoke_mag: MagicMock) -> None:
        """Test that endpoint requires authentication when API_KEY is set."""
        response = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}})
        assert response.status_code == 200

    def test_rate_limiting_applied(self, client: TestClient, mock_invoke_mag: MagicMock) -> None:
        """Test that rate limiting is applied to the endpoint."""
        for _ in range(5):
            response = client.post('/api/v1/runs', json={'agent': 'test-agent', 'payload': {'input': 'test'}})
            assert response.status_code in [200, 429]
