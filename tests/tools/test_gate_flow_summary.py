from __future__ import annotations

import json
from pathlib import Path

import pytest

from agdd.governance.gate import evaluate


@pytest.fixture()
def summary_file(tmp_path: Path) -> Path:
    payload = {
        "runs": 1,
        "successes": 1,
        "success_rate": 1.0,
        "avg_latency_ms": 1200.0,
        "errors": {"total": 0, "by_type": {}},
        "mcp": {
            "calls": 1,
            "errors": 0,
            "tokens": {"input": 50, "output": 25, "total": 75},
            "cost_usd": 0.05,
        },
        "steps": [
            {
                "name": "alpha",
                "runs": 1,
                "successes": 1,
                "errors": 0,
                "success_rate": 1.0,
                "avg_latency_ms": 1200.0,
                "mcp": {"calls": 1, "errors": 0},
                "models": ["gpt-4o-mini"],
            }
        ],
        "models": [
            {
                "name": "gpt-4o-mini",
                "calls": 1,
                "errors": 0,
                "tokens": {"input": 50, "output": 25, "total": 75},
                "cost_usd": 0.05,
            }
        ],
    }
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture()
def policy_file(tmp_path: Path) -> Path:
    policy = (
        "min_success_rate: 0.9\n"
        "max_avg_latency_ms: 2500\n"
        "per_step:\n"
        "  default:\n"
        "    max_error_rate: 0.2\n"
    )
    path = tmp_path / "policy.yaml"
    path.write_text(policy, encoding="utf-8")
    return path


def test_evaluate_pass(summary_file: Path, policy_file: Path) -> None:
    issues = evaluate(summary_file, policy_file)
    assert issues == []


def test_evaluate_fail_on_latency(summary_file: Path, policy_file: Path) -> None:
    policy_file.write_text("max_avg_latency_ms: 200\n", encoding="utf-8")
    issues = evaluate(summary_file, policy_file)
    assert issues and "avg_latency_ms" in issues[0]
