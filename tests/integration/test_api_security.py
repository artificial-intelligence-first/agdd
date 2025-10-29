"""Security tests for API endpoints."""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agdd.api.config import Settings, get_settings
from agdd.api.server import app


pytestmark = pytest.mark.slow

@pytest.fixture
def test_runs_dir(tmp_path: Path) -> Path:
    """Create a temporary runs directory with test data."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    # Create a valid test run
    valid_run = runs_dir / "mag-test-run-123"
    valid_run.mkdir()
    (valid_run / "summary.json").write_text(json.dumps({"slug": "test-agent", "status": "completed"}))
    (valid_run / "metrics.json").write_text(json.dumps({"duration": 1.5}))
    (valid_run / "logs.jsonl").write_text('{"level": "info", "message": "test log"}\n')

    return runs_dir


@pytest.fixture
def client_with_runs_dir(test_runs_dir: Path) -> Iterator[TestClient]:
    """Create test client with custom runs directory."""
    def override_settings() -> Settings:
        s = Settings()
        s.RUNS_BASE_DIR = str(test_runs_dir)
        return s

    app.dependency_overrides[get_settings] = override_settings
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestDirectoryTraversalProtection:
    """Test that directory traversal attacks are blocked."""

    def test_get_run_blocks_parent_directory_traversal(self, client_with_runs_dir: TestClient) -> None:
        """Test that ../../../../etc is blocked in get_run."""
        # FastAPI normalizes paths, so this may return 404 instead of reaching handler
        # Both 400 and 404 are acceptable security responses
        response = client_with_runs_dir.get("/api/v1/runs/../../../../etc")
        assert response.status_code in [400, 404]
        if response.status_code == 400:
            data = response.json()
            assert data["code"] == "invalid_run_id"

    def test_get_run_blocks_absolute_path(self, client_with_runs_dir: TestClient) -> None:
        """Test that absolute paths are blocked."""
        # FastAPI routing may handle this before reaching our handler
        response = client_with_runs_dir.get("/api/v1/runs//etc/passwd")
        assert response.status_code in [400, 404]

    def test_get_run_blocks_relative_path_components(self, client_with_runs_dir: TestClient) -> None:
        """Test that relative path components are blocked."""
        # FastAPI normalizes paths, resulting in 404
        response = client_with_runs_dir.get("/api/v1/runs/../../../etc")
        assert response.status_code in [400, 404]

    def test_get_run_blocks_windows_path_separators(self, client_with_runs_dir: TestClient) -> None:
        """Test that Windows-style path separators in run_id are blocked."""
        # URL-encode backslashes to test handler validation
        import urllib.parse
        run_id = urllib.parse.quote("..\\..\\..\\etc", safe="")
        response = client_with_runs_dir.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "invalid_run_id"

    def test_get_run_blocks_forward_slash(self, client_with_runs_dir: TestClient) -> None:
        """Test that forward slashes in run_id are blocked."""
        # FastAPI routing interprets this as separate path segments, so 404 is expected
        response = client_with_runs_dir.get("/api/v1/runs/subdir/run123")
        # This will be caught by routing layer (404), not our handler
        assert response.status_code == 404

    def test_get_run_blocks_url_encoded_path_separator(self, client_with_runs_dir: TestClient) -> None:
        """Test that URL-encoded forward slashes in run_id are blocked."""
        # URL-encode forward slash - FastAPI still normalizes these
        import urllib.parse
        run_id = urllib.parse.quote("subdir/run123", safe="")
        response = client_with_runs_dir.get(f"/api/v1/runs/{run_id}")
        # Both 400 and 404 are secure responses
        assert response.status_code in [400, 404]
        if response.status_code == 400:
            data = response.json()
            assert data["code"] == "invalid_run_id"

    def test_get_logs_blocks_directory_traversal(self, client_with_runs_dir: TestClient) -> None:
        """Test that directory traversal is blocked in get_logs."""
        # FastAPI routing normalizes this to /api/v1/runs/{something}/logs
        response = client_with_runs_dir.get("/api/v1/runs/../../../../etc/logs")
        assert response.status_code in [400, 404]

    def test_get_logs_blocks_path_separators(self, client_with_runs_dir: TestClient) -> None:
        """Test that path separators are blocked in get_logs."""
        # FastAPI routing handles this, expecting 404
        response = client_with_runs_dir.get("/api/v1/runs/../sensitive/logs")
        assert response.status_code in [400, 404]

    def test_get_logs_blocks_url_encoded_traversal(self, client_with_runs_dir: TestClient) -> None:
        """Test that URL-encoded directory traversal is blocked in get_logs."""
        import urllib.parse
        run_id = urllib.parse.quote("../../etc", safe="")
        response = client_with_runs_dir.get(f"/api/v1/runs/{run_id}/logs")
        # Both 400 and 404 are secure responses
        assert response.status_code in [400, 404]
        if response.status_code == 400:
            data = response.json()
            assert data["code"] == "invalid_run_id"


class TestValidRunIdFormats:
    """Test that valid run_id formats work correctly."""

    def test_get_run_accepts_valid_alphanumeric(self, client_with_runs_dir: TestClient) -> None:
        """Test that valid alphanumeric run_id works."""
        response = client_with_runs_dir.get("/api/v1/runs/mag-test-run-123")
        # Should not get 400 validation error (may get 404 or 200 depending on data)
        assert response.status_code in [200, 404]
        if response.status_code == 404:
            data = response.json()
            # Should be not_found, not invalid_run_id
            assert data["code"] == "not_found"

    def test_get_run_accepts_run_with_hyphens(self, client_with_runs_dir: TestClient) -> None:
        """Test that run_id with hyphens is accepted."""
        response = client_with_runs_dir.get("/api/v1/runs/mag-test-run-123")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "mag-test-run-123"
        assert data["has_logs"] is True

    def test_get_logs_accepts_valid_run_id(self, client_with_runs_dir: TestClient) -> None:
        """Test that valid run_id works in get_logs."""
        response = client_with_runs_dir.get("/api/v1/runs/mag-test-run-123/logs?tail=5")
        assert response.status_code == 200
        # Should return log content
        content = response.text
        assert "test log" in content

    def test_run_id_max_length_accepted(self, client_with_runs_dir: TestClient, test_runs_dir: Path) -> None:
        """Test that run_id with 128 characters is accepted."""
        # Create run with 128-character name
        long_name = "a" * 128
        long_run = test_runs_dir / long_name
        long_run.mkdir()
        (long_run / "summary.json").write_text(json.dumps({"slug": "test"}))

        response = client_with_runs_dir.get(f"/api/v1/runs/{long_name}")
        assert response.status_code == 200

    def test_run_id_exceeding_max_length_rejected(self, client_with_runs_dir: TestClient) -> None:
        """Test that run_id with >128 characters is rejected."""
        long_name = "a" * 129
        response = client_with_runs_dir.get(f"/api/v1/runs/{long_name}")
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "invalid_run_id"


class TestRunTrackerValidation:
    """Test run_tracker validation functions directly."""

    def test_validate_run_id_accepts_valid(self) -> None:
        """Test that validate_run_id accepts valid formats."""
        from agdd.api.run_tracker import validate_run_id

        # Should not raise
        validate_run_id("mag-test-123")
        validate_run_id("test123")
        validate_run_id("a" * 128)

    def test_validate_run_id_rejects_traversal(self) -> None:
        """Test that validate_run_id rejects directory traversal."""
        from agdd.api.run_tracker import validate_run_id

        with pytest.raises(ValueError, match="Invalid run_id"):
            validate_run_id("../../../../etc")

        with pytest.raises(ValueError, match="Invalid run_id"):
            validate_run_id("../etc")

        with pytest.raises(ValueError, match="Invalid run_id"):
            validate_run_id("..")

    def test_validate_run_id_rejects_path_separators(self) -> None:
        """Test that validate_run_id rejects path separators."""
        from agdd.api.run_tracker import validate_run_id

        # Path separators are rejected by the regex pattern check
        with pytest.raises(ValueError, match="Invalid run_id"):
            validate_run_id("subdir/run123")

        with pytest.raises(ValueError, match="Invalid run_id"):
            validate_run_id("subdir\\run123")

    def test_safe_run_path_rejects_traversal(self, tmp_path: Path) -> None:
        """Test that _safe_run_path verifies resolved path is within base_dir."""
        from agdd.api.run_tracker import _safe_run_path

        base_dir = tmp_path / "runs"
        base_dir.mkdir()

        # This should fail validation before path resolution
        with pytest.raises(ValueError, match="Invalid run_id"):
            _safe_run_path(base_dir, "../../../../etc")

    def test_safe_run_path_accepts_valid(self, tmp_path: Path) -> None:
        """Test that _safe_run_path accepts valid run_id."""
        from agdd.api.run_tracker import _safe_run_path

        base_dir = tmp_path / "runs"
        base_dir.mkdir()

        run_path = _safe_run_path(base_dir, "mag-test-123")
        assert run_path.parent == base_dir.resolve()
        assert run_path.name == "mag-test-123"
