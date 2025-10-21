from __future__ import annotations

import json
from typer.testing import CliRunner

from agdd.cli import app

runner = CliRunner()


def test_agent_run_command_succeeds() -> None:
    """Test that agent run command executes successfully"""
    payload = json.dumps({"role": "Engineer", "level": "Mid", "location": "Remote", "experience_years": 5})
    result = runner.invoke(app, ["agent", "run", "offer-orchestrator-mag"], input=payload)
    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert "offer" in output
    assert "metadata" in output


def test_flow_available_command() -> None:
    """Test that flow available command runs without error"""
    result = runner.invoke(app, ["flow", "available"])
    assert result.exit_code == 0
