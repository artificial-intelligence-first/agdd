from __future__ import annotations

import json
import pytest
from typer.testing import CliRunner

from magsag.cli import app

runner = CliRunner()


@pytest.mark.slow
def test_agent_run_command_succeeds() -> None:
    """Test that agent run command executes successfully.

    This test performs actual agent execution with LLM calls, which can take
    30+ seconds. Marked as 'slow' to allow quick CI runs with `-m "not slow"`.
    """
    payload = json.dumps(
        {"role": "Engineer", "level": "Mid", "location": "Remote", "experience_years": 5}
    )
    result = runner.invoke(app, ["agent", "run", "offer-orchestrator-mag"], input=payload)
    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert "offer" in output
    assert "metadata" in output


def test_flow_available_command() -> None:
    """Test that flow available command runs without error"""
    result = runner.invoke(app, ["flow", "available"])
    assert result.exit_code == 0
