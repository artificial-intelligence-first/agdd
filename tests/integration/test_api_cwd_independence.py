"""Test agent listing works from different working directories."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from magsag.api.server import app


import pytest

pytestmark = pytest.mark.slow


def test_list_agents_from_different_cwd(tmp_path: Path) -> None:
    """Test that agent listing works when API is run from outside repository root."""
    # Save original CWD
    original_cwd = os.getcwd()

    try:
        # Change to a different directory (simulates running from outside repo)
        os.chdir(tmp_path)

        # Create test client (this will import/load the API)
        client = TestClient(app)

        # List agents - should still work because we use package-relative paths
        response = client.get("/api/v1/agents")

        assert response.status_code == 200
        agents = response.json()
        assert isinstance(agents, list)

        # Should find agents even though CWD is different
        assert len(agents) > 0, "Should find agents even when CWD is not repository root"

        # Verify we can find the expected agent
        agent_slugs = [a["slug"] for a in agents]
        assert "offer-orchestrator-mag" in agent_slugs

    finally:
        # Restore original CWD
        os.chdir(original_cwd)
