from __future__ import annotations

from magsag.runners.flowrunner import FlowRunner


def test_flow_runner_info_capabilities() -> None:
    info = FlowRunner().info()
    assert info.name == "flow-runner"
    assert "dry-run" in info.capabilities
    assert "artifacts" in info.capabilities
