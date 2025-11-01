"""Integration test for custom RUNS_BASE_DIR setting."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from magsag.api.config import Settings, get_settings
from magsag.api.server import app


import pytest

pytestmark = pytest.mark.slow


def test_custom_runs_base_dir(tmp_path: Path) -> None:
    """Test that custom RUNS_BASE_DIR is honored for both execution and tracking."""
    custom_runs_dir = tmp_path / "custom_runs"
    custom_runs_dir.mkdir()

    # Override settings to use custom runs directory
    def override_settings() -> Settings:
        s = Settings()
        s.RUNS_BASE_DIR = str(custom_runs_dir)
        return s

    app.dependency_overrides[get_settings] = override_settings
    test_client = TestClient(app)

    try:
        # Execute agent
        response = test_client.post(
            "/api/v1/agents/offer-orchestrator-mag/run",
            json={"payload": {"role": "Engineer", "level": "Mid", "experience_years": 3}},
        )

        assert response.status_code == 200
        data = response.json()

        # Should get a run_id
        run_id = data.get("run_id")
        assert run_id is not None, "run_id should be found when using custom RUNS_BASE_DIR"

        # Verify run artifacts exist in custom directory
        run_dir = custom_runs_dir / run_id
        assert run_dir.exists(), f"Run directory should exist at {run_dir}"
        assert (run_dir / "logs.jsonl").exists(), "logs.jsonl should exist"
        assert (run_dir / "metrics.json").exists(), "metrics.json should exist"
        assert (run_dir / "summary.json").exists(), "summary.json should exist"

        # Verify artifacts are accessible via API
        summary_response = test_client.get(f"/api/v1/runs/{run_id}")
        assert summary_response.status_code == 200

        logs_response = test_client.get(f"/api/v1/runs/{run_id}/logs?tail=5")
        assert logs_response.status_code == 200

    finally:
        app.dependency_overrides.clear()
