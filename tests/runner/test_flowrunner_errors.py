"""Tests for FlowRunner error handling."""

from __future__ import annotations

from pathlib import Path

from magsag.runners.flowrunner import FlowRunner


def test_flowrunner_unavailable() -> None:
    """Test that FlowRunner handles unavailable executable gracefully."""
    runner = FlowRunner(exe="nonexistent-command-xyz")
    assert not runner.is_available()


def test_flowrunner_run_when_unavailable() -> None:
    """Test that run returns error when flowctl is not available."""
    runner = FlowRunner(exe="nonexistent-command-xyz")
    result = runner.run(Path("test.yaml"))
    assert not result.ok
    assert "not installed" in result.stderr


def test_flowrunner_validate_when_unavailable() -> None:
    """Test that validate returns error when flowctl is not available."""
    runner = FlowRunner(exe="nonexistent-command-xyz")
    result = runner.validate(Path("test.yaml"))
    assert not result.ok
    assert "not installed" in result.stderr
