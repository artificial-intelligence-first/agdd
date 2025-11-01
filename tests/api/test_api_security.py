"""Unit and integration tests for API RBAC scope checks."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from magsag.api.config import Settings, get_settings
from magsag.api.security import get_scopes_for_key, require_scope
from magsag.api.server import app


class TestGetScopesForKey:
    """Test get_scopes_for_key function."""

    def test_returns_all_scopes_for_any_key(self) -> None:
        """Test that get_scopes_for_key returns all scopes (mock implementation)."""
        scopes = get_scopes_for_key("test-api-key-123")
        assert isinstance(scopes, list)
        assert "agents:run" in scopes
        assert "agents:read" in scopes
        assert "runs:read" in scopes
        assert "runs:logs" in scopes

    def test_returns_consistent_scopes(self) -> None:
        """Test that same key returns same scopes."""
        scopes1 = get_scopes_for_key("test-key")
        scopes2 = get_scopes_for_key("test-key")
        assert scopes1 == scopes2


class TestRequireScopeFunction:
    """Test require_scope function and dependency."""

    @pytest.mark.asyncio
    async def test_require_scope_returns_dependency_callable(self) -> None:
        """Test that require_scope returns a callable dependency."""
        dependency = require_scope(["agents:run"])
        assert callable(dependency)

    @pytest.mark.asyncio
    async def test_scope_check_allows_access_with_valid_scopes(self) -> None:
        """Test that scope check passes when user has required scopes."""
        # Create a mock settings with no API key (dev mode)
        mock_settings = Settings()
        mock_settings.API_KEY = None

        dependency_func = require_scope(["agents:run"])

        # Call dependency - should not raise
        result = await dependency_func(
            credentials=None,
            x_api_key=None,
            settings=mock_settings,
        )
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_scope_check_blocks_access_with_missing_scopes(self) -> None:
        """Test that scope check fails when required scopes are missing."""
        # Mock get_scopes_for_key to return limited scopes
        with patch("magsag.api.security.get_scopes_for_key") as mock_get_scopes:
            mock_get_scopes.return_value = ["runs:read"]  # Missing agents:run

            mock_settings = Settings()
            mock_settings.API_KEY = None

            dependency_func = require_scope(["agents:run"])

            with pytest.raises(HTTPException) as exc_info:
                await dependency_func(
                    credentials=None,
                    x_api_key=None,
                    settings=mock_settings,
                )

            assert exc_info.value.status_code == 403
            detail = exc_info.value.detail
            assert isinstance(detail, dict)
            assert detail["code"] == "insufficient_permissions"
            missing_scopes = detail.get("missing_scopes")
            assert isinstance(missing_scopes, list)
            assert "agents:run" in missing_scopes

    @pytest.mark.asyncio
    async def test_scope_check_validates_api_key_first(self) -> None:
        """Test that invalid API key is rejected before scope check."""
        mock_settings = Settings()
        mock_settings.API_KEY = "correct-key"

        dependency_func = require_scope(["agents:run"])

        with pytest.raises(HTTPException) as exc_info:
            await dependency_func(
                credentials=None,
                x_api_key="wrong-key",
                settings=mock_settings,
            )

        assert exc_info.value.status_code == 401
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert detail["code"] == "unauthorized"


@pytest.fixture
def client_with_auth() -> Iterator[TestClient]:
    """Create test client with API key disabled (dev mode)."""

    def override_settings() -> Settings:
        s = Settings()
        s.API_KEY = None  # Disable auth for testing
        return s

    app.dependency_overrides[get_settings] = override_settings
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def client_with_limited_scopes() -> Iterator[TestClient]:
    """Create test client with limited scopes (simulating restricted access)."""

    def override_settings() -> Settings:
        s = Settings()
        s.API_KEY = None  # Disable auth for testing
        return s

    app.dependency_overrides[get_settings] = override_settings

    # Mock get_scopes_for_key to return limited scopes
    with patch("magsag.api.security.get_scopes_for_key") as mock_get_scopes:
        mock_get_scopes.return_value = ["runs:read"]  # Only runs:read scope

        client = TestClient(app)
        yield client

    app.dependency_overrides.clear()


class TestAgentEndpointsRBACScopes:
    """Test that agent endpoints enforce RBAC scopes."""

    def test_list_agents_requires_agents_read_scope(
        self, client_with_limited_scopes: TestClient
    ) -> None:
        """Test that GET /agents requires agents:read scope."""
        response = client_with_limited_scopes.get("/api/v1/agents")

        # Should be blocked due to missing agents:read scope
        assert response.status_code == 403
        data = response.json()
        assert data["code"] == "insufficient_permissions"
        assert "agents:read" in data["missing_scopes"]

    def test_list_agents_succeeds_with_valid_scopes(
        self, client_with_auth: TestClient
    ) -> None:
        """Test that GET /agents succeeds with valid scopes."""
        response = client_with_auth.get("/api/v1/agents")

        # Should succeed (mock returns all scopes)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_run_agent_requires_agents_run_scope(
        self, client_with_limited_scopes: TestClient
    ) -> None:
        """Test that POST /agents/{slug}/run requires agents:run scope."""
        response = client_with_limited_scopes.post(
            "/api/v1/agents/test-agent/run",
            json={"payload": {"input": "test"}},
        )

        # Should be blocked due to missing agents:run scope
        assert response.status_code == 403
        data = response.json()
        assert data["code"] == "insufficient_permissions"
        assert "agents:run" in data["missing_scopes"]

    def test_run_agent_succeeds_with_valid_scopes(
        self, client_with_auth: TestClient
    ) -> None:
        """Test that POST /agents/{slug}/run succeeds with valid scopes."""
        # This will fail with 404 (agent not found) but not 403 (scope error)
        response = client_with_auth.post(
            "/api/v1/agents/nonexistent-agent/run",
            json={"payload": {"input": "test"}},
        )

        # Should not be 403 (scope check passed)
        assert response.status_code != 403


class TestRunEndpointsRBACScopes:
    """Test that run endpoints enforce RBAC scopes."""

    def test_get_run_requires_runs_read_scope(
        self, client_with_limited_scopes: TestClient
    ) -> None:
        """Test that GET /runs/{run_id} requires runs:read scope."""
        # This should succeed since our limited client has runs:read
        response = client_with_limited_scopes.get("/api/v1/runs/test-run-123")

        # Should not be 403 (has required scope)
        # May be 404 (run not found) but not 403
        assert response.status_code != 403

    def test_get_run_succeeds_with_valid_scopes(
        self, client_with_auth: TestClient
    ) -> None:
        """Test that GET /runs/{run_id} succeeds with valid scopes."""
        response = client_with_auth.get("/api/v1/runs/test-run-123")

        # Should not be 403 (scope check passed)
        assert response.status_code != 403

    def test_get_logs_requires_runs_logs_scope(self, client_with_auth: TestClient) -> None:
        """Test that GET /runs/{run_id}/logs requires runs:logs scope."""
        # Create client with scopes but missing runs:logs
        def override_settings() -> Settings:
            s = Settings()
            s.API_KEY = None
            return s

        app.dependency_overrides[get_settings] = override_settings

        with patch("magsag.api.security.get_scopes_for_key") as mock_get_scopes:
            mock_get_scopes.return_value = ["runs:read"]  # Missing runs:logs

            client = TestClient(app)
            response = client.get("/api/v1/runs/test-run-123/logs")

            # Should be blocked due to missing runs:logs scope
            assert response.status_code == 403
            data = response.json()
            assert data["code"] == "insufficient_permissions"
            assert "runs:logs" in data["missing_scopes"]

        app.dependency_overrides.clear()

    def test_get_logs_succeeds_with_valid_scopes(
        self, client_with_auth: TestClient
    ) -> None:
        """Test that GET /runs/{run_id}/logs succeeds with valid scopes."""
        response = client_with_auth.get("/api/v1/runs/test-run-123/logs")

        # Should not be 403 (scope check passed)
        # May be 404 (logs not found) but not 403
        assert response.status_code != 403


class TestScopeErrorDetails:
    """Test that scope errors provide detailed information."""

    def test_insufficient_permissions_error_includes_required_scopes(
        self, client_with_limited_scopes: TestClient
    ) -> None:
        """Test that 403 error includes required and missing scopes."""
        response = client_with_limited_scopes.get("/api/v1/agents")

        assert response.status_code == 403
        data = response.json()
        assert "required_scopes" in data
        assert "missing_scopes" in data
        assert isinstance(data["required_scopes"], list)
        assert isinstance(data["missing_scopes"], list)

    def test_error_message_is_descriptive(
        self, client_with_limited_scopes: TestClient
    ) -> None:
        """Test that error message clearly indicates missing scopes."""
        response = client_with_limited_scopes.post(
            "/api/v1/agents/test/run",
            json={"payload": {}},
        )

        assert response.status_code == 403
        data = response.json()
        assert "message" in data
        assert "Missing required scopes" in data["message"]
