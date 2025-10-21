from __future__ import annotations

from typer.testing import CliRunner

from agdd.cli import app

runner = CliRunner()


def test_validate_command_succeeds() -> None:
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0
    assert "Validated" in result.stdout


def test_run_command_executes_echo_skill() -> None:
    result = runner.invoke(app, ["run", "hello", "--text", "AGDD"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "AGDD"


def test_run_command_accepts_positional_text() -> None:
    result = runner.invoke(app, ["run", "hello", "AGDD"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "AGDD"
