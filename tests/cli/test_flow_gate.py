from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agdd.cli", *args], capture_output=True, text=True, check=False
    )


def test_flow_gate_cli(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    policy = tmp_path / "policy.yaml"

    summary.write_text(
        json.dumps(
            {
                "runs": 1,
                "successes": 1,
                "success_rate": 1.0,
                "avg_latency_ms": 100.0,
                "errors": {"total": 0, "by_type": {}},
                "mcp": {
                    "calls": 1,
                    "errors": 0,
                    "tokens": {"input": 10, "output": 5, "total": 15},
                    "cost_usd": 0.01,
                },
                "steps": [
                    {
                        "name": "alpha",
                        "runs": 1,
                        "successes": 1,
                        "errors": 0,
                        "success_rate": 1.0,
                        "avg_latency_ms": 100.0,
                        "mcp": {"calls": 1, "errors": 0},
                    }
                ],
                "models": [
                    {
                        "name": "mock-model",
                        "calls": 1,
                        "errors": 0,
                        "tokens": {"input": 10, "output": 5, "total": 15},
                        "cost_usd": 0.01,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    policy.write_text("min_success_rate: 0.9\n", encoding="utf-8")

    cp = _run_cli("flow", "gate", str(summary), "--policy", str(policy))
    assert cp.returncode == 0
    assert "PASSED" in cp.stdout

    policy.write_text("min_success_rate: 1.1\n", encoding="utf-8")
    cp = _run_cli("flow", "gate", str(summary), "--policy", str(policy))
    assert cp.returncode == 2
    assert "FAILED" in cp.stdout


def test_flow_gate_uses_bundled_policy(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "runs": 1,
                "successes": 1,
                "success_rate": 1.0,
                "avg_latency_ms": 100.0,
                "errors": {"total": 0, "by_type": {}},
                "mcp": {
                    "calls": 1,
                    "errors": 0,
                    "tokens": {"input": 10, "output": 5, "total": 15},
                    "cost_usd": 0.01,
                },
                "steps": [
                    {
                        "name": "hello",
                        "runs": 1,
                        "successes": 1,
                        "errors": 0,
                        "success_rate": 1.0,
                        "avg_latency_ms": 100.0,
                        "mcp": {"calls": 1, "errors": 0},
                    }
                ],
                "models": [
                    {
                        "name": "mock-model",
                        "calls": 1,
                        "errors": 0,
                        "tokens": {"input": 10, "output": 5, "total": 15},
                        "cost_usd": 0.01,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cp = _run_cli("flow", "gate", str(summary))
    assert cp.returncode == 0
