"""Summarize Flow Runner execution artifacts."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

_SUCCESS_STATUSES = {"ok", "success", "succeeded", "completed"}


@dataclass(slots=True)
class StepMetrics:
    runs: int = 0
    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    mcp_calls: int = 0
    mcp_errors: int = 0
    models: set[str] = field(default_factory=set)
    error_categories: Dict[str, int] = field(default_factory=lambda: defaultdict(int))


@dataclass(slots=True)
class ModelStats:
    calls: int = 0
    errors: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


@dataclass(slots=True)
class RunMetrics:
    succeeded: int = 0
    total_latency_ms: float = 0.0
    completed_steps: int = 0
    error_categories: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    step_stats: Dict[str, StepMetrics] = field(default_factory=dict)
    mcp_calls: int = 0
    mcp_errors: int = 0
    model_stats: Dict[str, ModelStats] = field(default_factory=dict)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        return data
    return None


def _extract_model(record: dict[str, Any]) -> str:
    """
    Extract model name from various possible locations in a record.

    Searches in order: model, model_name, usage.model, config.model.
    Returns "unknown" if no model name is found.
    """
    for key in ("model", "model_name"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    usage = record.get("usage")
    if isinstance(usage, dict):
        value = usage.get("model")
        if isinstance(value, str) and value:
            return value
    config = record.get("config")
    if isinstance(config, dict):
        value = config.get("model")
        if isinstance(value, str) and value:
            return value
    return "unknown"


def _aggregate_mcp_logs(run_dir: Path, metrics: RunMetrics) -> None:
    path = run_dir / "mcp_calls.jsonl"
    if not path.exists():
        return

    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            metrics.mcp_calls += 1
            status = str(record.get("status", "")).lower()
            is_success = status in {"ok", "success"}
            if not is_success:
                metrics.mcp_errors += 1

            model_name = _extract_model(record)
            stats = metrics.model_stats.setdefault(model_name, ModelStats())
            stats.calls += 1
            if not is_success:
                stats.errors += 1

            usage = record.get("usage")
            if isinstance(usage, dict):
                stats.input_tokens += int(usage.get("input_tokens", 0) or 0)
                stats.output_tokens += int(usage.get("output_tokens", 0) or 0)
                stats.total_tokens += int(usage.get("total_tokens", 0) or 0)
                cost = usage.get("cost_usd")
                if isinstance(cost, (int, float)):
                    stats.cost_usd += float(cost)

            for key in ("input_tokens", "output_tokens", "total_tokens"):
                value = record.get(key)
                if isinstance(value, (int, float)):
                    setattr(stats, key, getattr(stats, key) + int(value))

            cost = record.get("cost_usd")
            if isinstance(cost, (int, float)):
                stats.cost_usd += float(cost)


def _classify_error(record: dict[str, Any], extra: dict[str, Any] | None) -> str:
    """
    Classify an error based on error information in the record.

    Extracts error tokens from various fields and matches against known error patterns.
    Returns one of: timeout, tool, validation, rate_limit, or unknown.
    """
    tokens: list[str] = []

    for key in ("error_type", "error_code", "status"):
        value = record.get(key)
        if isinstance(value, str):
            tokens.append(value.lower())

    error_obj = record.get("error")
    if isinstance(error_obj, dict):
        for key in ("type", "code", "category", "reason"):
            value = error_obj.get(key)
            if isinstance(value, str):
                tokens.append(value.lower())
        message = error_obj.get("message")
        if isinstance(message, str):
            tokens.append(message.lower())
    elif isinstance(error_obj, str):
        tokens.append(error_obj.lower())

    if isinstance(extra, dict):
        err = extra.get("error")
        if isinstance(err, dict):
            for key in ("type", "code", "category", "reason"):
                value = err.get(key)
                if isinstance(value, str):
                    tokens.append(value.lower())
            message = err.get("message")
            if isinstance(message, str):
                tokens.append(message.lower())
        elif isinstance(err, str):
            tokens.append(err.lower())

    classifiers = (
        ("timeout", ("timeout", "deadline")),
        ("tool", ("tool", "tools")),
        ("validation", ("validation", "schema", "invalid")),
        ("rate_limit", ("rate limit", "ratelimit", "throttle", "429")),
    )
    for name, keywords in classifiers:
        if any(keyword in token for token in tokens for keyword in keywords):
            return name
    return "unknown"


def _accumulate_metrics(run_dir: Path, metrics: RunMetrics) -> bool:
    path = run_dir / "runs.jsonl"
    if not path.exists():
        return False

    run_failed = False
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if record.get("event") != "end":
                continue

            step = record.get("step")
            if not isinstance(step, str) or not step:
                continue

            raw_status = record.get("status")
            status = str(raw_status).lower() if isinstance(raw_status, str) else ""
            latency = record.get("latency_ms")

            step_metrics = metrics.step_stats.setdefault(step, StepMetrics())
            step_metrics.runs += 1
            if isinstance(latency, (int, float)):
                step_metrics.total_latency_ms += float(latency)
                metrics.total_latency_ms += float(latency)
                metrics.completed_steps += 1

            extra = record.get("extra")
            if isinstance(extra, dict):
                model = extra.get("model")
                if isinstance(model, str) and model:
                    step_metrics.models.add(model)
                if extra.get("type") == "mcp":
                    step_metrics.mcp_calls += 1
                    if status != "ok":
                        step_metrics.mcp_errors += 1

            if status in _SUCCESS_STATUSES:
                step_metrics.successes += 1
            else:
                step_metrics.failures += 1
                category = _classify_error(record, extra if isinstance(extra, dict) else None)
                step_metrics.error_categories[category] += 1
                metrics.error_categories[category] += 1
                run_failed = True

    return run_failed


def _summary_success(summary: dict[str, Any]) -> bool:
    failures = summary.get("failures")
    if isinstance(failures, dict):
        if all(not value for value in failures.values()):
            return True
        return False
    if isinstance(failures, list):
        if not failures:
            return True
        return False
    # If failures is None or False, treat as success
    if failures in (None, False):
        return True

    status_fields = (
        summary.get("status"),
        summary.get("result"),
    )
    for status_field in status_fields:
        if isinstance(status_field, str) and status_field.lower() in _SUCCESS_STATUSES:
            return True
    return False


def summarize(base: Path | None = None) -> Dict[str, Any]:
    """Return aggregate statistics for Flow Runner runs."""
    root = base or Path(".runs")
    if not root.exists():
        return {
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

    runs = [path for path in root.iterdir() if path.is_dir()]
    total_runs = len(runs)
    metrics = RunMetrics()

    for run_dir in runs:
        run_summary = _load_json(run_dir / "summary.json")
        if run_summary is None:
            continue

        run_failed = _accumulate_metrics(run_dir, metrics)
        summary_success = _summary_success(run_summary)
        if summary_success or not run_failed:
            metrics.succeeded += 1
        _aggregate_mcp_logs(run_dir, metrics)

    success_rate = (metrics.succeeded / total_runs) if total_runs else 0.0
    avg_latency = (
        metrics.total_latency_ms / metrics.completed_steps if metrics.completed_steps else 0.0
    )

    steps = []
    total_failures = 0
    for step, data in sorted(metrics.step_stats.items()):
        entry: Dict[str, Any] = {
            "name": step,
            "runs": data.runs,
            "successes": data.successes,
            "errors": data.failures,
            "success_rate": (data.successes / data.runs) if data.runs else 0.0,
            "avg_latency_ms": (data.total_latency_ms / data.runs) if data.runs else 0.0,
        }
        total_failures += data.failures
        if data.mcp_calls or data.mcp_errors:
            entry["mcp"] = {"calls": data.mcp_calls, "errors": data.mcp_errors}
        if data.models:
            entry["models"] = sorted(data.models)
        if data.error_categories:
            entry["error_types"] = dict(sorted(data.error_categories.items()))
        steps.append(entry)

    # Fallback: aggregate MCP metrics from steps if not directly provided
    if metrics.mcp_calls == 0:
        metrics.mcp_calls = sum(data.mcp_calls for data in metrics.step_stats.values())
    if metrics.mcp_errors == 0:
        metrics.mcp_errors = sum(data.mcp_errors for data in metrics.step_stats.values())

    total_input_tokens = 0
    total_output_tokens = 0
    total_tokens = 0
    total_cost = 0.0
    models = []
    for model_name, stats in sorted(metrics.model_stats.items()):
        model_entry = {
            "name": model_name,
            "calls": stats.calls,
            "errors": stats.errors,
            "tokens": {
                "input": stats.input_tokens,
                "output": stats.output_tokens,
                "total": stats.total_tokens,
            },
            "cost_usd": stats.cost_usd,
        }
        models.append(model_entry)
        total_input_tokens += stats.input_tokens
        total_output_tokens += stats.output_tokens
        total_tokens += stats.total_tokens
        total_cost += stats.cost_usd

    errors = {
        "total": total_failures,
        "by_type": dict(sorted(metrics.error_categories.items())),
    }

    summary: Dict[str, Any] = {
        "runs": total_runs,
        "successes": metrics.succeeded,
        "success_rate": success_rate,
        "avg_latency_ms": avg_latency,
        "errors": errors,
        "mcp": {
            "calls": metrics.mcp_calls,
            "errors": metrics.mcp_errors,
            "tokens": {
                "input": total_input_tokens,
                "output": total_output_tokens,
                "total": total_tokens,
            },
            "cost_usd": total_cost,
        },
        "steps": steps,
        "models": models,
    }

    return summary


def main() -> None:
    result = summarize()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
