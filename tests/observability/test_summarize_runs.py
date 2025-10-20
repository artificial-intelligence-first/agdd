from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from observability.summarize_runs import summarize


def test_summarize_handles_missing_directory(tmp_path: Path) -> None:
    result = summarize(tmp_path / ".runs")
    assert result == {
        "runs": 0,
        "successes": 0,
        "success_rate": 0.0,
        "avg_latency_ms": 0.0,
        "errors": {"total": 0, "by_type": {}},
        "mcp": {
            "calls": 0,
            "errors": 0,
            "tokens": {"input": 0, "output": 0, "total": 0},
            "cost_usd": 0.0,
        },
        "steps": [],
        "models": [],
    }


def test_summarize_counts_successful_runs(tmp_path: Path) -> None:
    base = tmp_path / ".runs"
    base.mkdir()

    run_success = base / "run-success"
    run_success.mkdir()
    (run_success / "summary.json").write_text('{"failures": {}}', encoding="utf-8")
    (run_success / "runs.jsonl").write_text(
        '{"event": "end", "latency_ms": 10, "step": "alpha", "status": "ok", "extra": {"type": "shell"}}\n',
        encoding="utf-8",
    )

    run_failure = base / "run-failure"
    run_failure.mkdir()
    (run_failure / "summary.json").write_text('{"failures": {"step": "boom"}}', encoding="utf-8")
    (run_failure / "runs.jsonl").write_text(
        '{"event": "end", "latency_ms": 30, "step": "beta", "status": "failed", "extra": {"type": "mcp", "error": {"type": "timeout"}}}\n',
        encoding="utf-8",
    )
    (run_failure / "mcp_calls.jsonl").write_text(
        '{"model": "gpt-test", "status": "ok", "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150, "cost_usd": 0.12}}\n'
        '{"model": "gpt-test", "status": "error", "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}\n',
        encoding="utf-8",
    )

    result = summarize(base)
    assert result["runs"] == 2
    assert result["successes"] == 1
    assert result["success_rate"] == 0.5
    assert result["avg_latency_ms"] == 20.0
    assert result["mcp"] == {
        "calls": 2,
        "errors": 1,
        "tokens": {"input": 110, "output": 55, "total": 165},
        "cost_usd": 0.12,
    }
    assert result["steps"] == [
        {
            "name": "alpha",
            "runs": 1,
            "successes": 1,
            "errors": 0,
            "success_rate": 1.0,
            "avg_latency_ms": 10.0,
        },
        {
            "name": "beta",
            "runs": 1,
            "successes": 0,
            "errors": 1,
            "success_rate": 0.0,
            "avg_latency_ms": 30.0,
            "mcp": {"calls": 1, "errors": 1},
            "error_types": {"timeout": 1},
        },
    ]
    assert result["errors"] == {"total": 1, "by_type": {"timeout": 1}}
    assert result["models"] == [
        {
            "name": "gpt-test",
            "calls": 2,
            "errors": 1,
            "tokens": {"input": 110, "output": 55, "total": 165},
            "cost_usd": 0.12,
        }
    ]


def test_flow_summarize_cli_outputs_json(tmp_path: Path) -> None:
    base = tmp_path / ".runs"
    base.mkdir()
    run_dir = base / "run"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text('{"failures": {}}', encoding="utf-8")
    (run_dir / "runs.jsonl").write_text(
        '{"event": "end", "latency_ms": 5, "step": "alpha", "status": "ok", "extra": {"type": "shell"}}\n',
        encoding="utf-8",
    )

    destination = tmp_path / "report.json"

    cp = subprocess.run(
        [
            sys.executable,
            "-m",
            "agdd.cli",
            "flow",
            "summarize",
            "--base",
            str(base),
            "--output",
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert cp.returncode == 0
    payload = json.loads(cp.stdout)
    assert payload["runs"] == 1
    assert payload["successes"] == 1
    assert payload["avg_latency_ms"] == 5.0
    assert payload["steps"][0]["avg_latency_ms"] == 5.0
    assert json.loads(destination.read_text(encoding="utf-8"))["runs"] == 1
