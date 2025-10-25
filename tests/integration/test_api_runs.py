"""Integration tests for /runs API endpoints."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agdd.api.server import app

client = TestClient(app)


def test_get_run_not_found() -> None:
    """Test getting non-existent run returns 404."""
    response = client.get("/api/v1/runs/nonexistent-run-id")
    assert response.status_code == 404
    error = response.json()
    assert "code" in error
    assert error["code"] == "not_found"


def test_get_logs_not_found() -> None:
    """Test getting logs for non-existent run returns 404."""
    response = client.get("/api/v1/runs/nonexistent-run-id/logs")
    assert response.status_code == 404


@pytest.fixture
def temp_run_dir(tmp_path: Path) -> Path:
    """Create a temporary run directory with test artifacts."""
    run_id = "test-run-123"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)

    # Create summary.json
    summary = {"slug": "test-agent", "status": "success"}
    (run_dir / "summary.json").write_text(json.dumps(summary))

    # Create metrics.json
    metrics = {"latency_ms": 1000, "task_count": 1}
    (run_dir / "metrics.json").write_text(json.dumps(metrics))

    # Create logs.jsonl
    logs = [
        {"event": "start", "run_id": run_id},
        {"event": "end", "run_id": run_id},
    ]
    (run_dir / "logs.jsonl").write_text("\n".join(json.dumps(log) for log in logs))

    return tmp_path


def test_get_run_with_artifacts(temp_run_dir: Path) -> None:
    """Test getting run with all artifacts present."""
    # Override settings dependency to use temp directory
    from agdd.api.config import Settings, get_settings
    from agdd.api.server import app

    def override_settings() -> Settings:
        s = Settings()
        s.RUNS_BASE_DIR = str(temp_run_dir)
        return s

    app.dependency_overrides[get_settings] = override_settings
    test_client = TestClient(app)

    try:
        response = test_client.get("/api/v1/runs/test-run-123")
        assert response.status_code == 200

        data = response.json()
        assert data["run_id"] == "test-run-123"
        assert data["slug"] == "test-agent"
        assert data["has_logs"] is True
        assert "summary" in data
        assert "metrics" in data
    finally:
        app.dependency_overrides.clear()
