"""Governance gate evaluation for Flow Runner summaries."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import validate as jsonschema_validate

from importlib import resources

CONTRACTS_PACKAGE = "agdd.assets.contracts"
POLICIES_PACKAGE = "agdd.assets.policies"

_FLOW_SUMMARY_SCHEMA = json.loads(
    resources.files(CONTRACTS_PACKAGE)
    .joinpath("flow_summary.schema.json")
    .read_text(encoding="utf-8")
)
_DEFAULT_POLICY_TEXT = (
    resources.files(POLICIES_PACKAGE)
    .joinpath("flow_governance.yaml")
    .read_text(encoding="utf-8")
)


def _ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if denominator in (None, 0):
        return None
    if numerator is None:
        return None
    return float(numerator) / float(denominator)


def _match_pattern(value: str, pattern: str) -> bool:
    if pattern.endswith("*"):
        return value.startswith(pattern[:-1])
    return value == pattern


def _load_summary(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    jsonschema_validate(instance=data, schema=_FLOW_SUMMARY_SCHEMA)
    return data


def _load_policy(path: Path | None) -> dict[str, Any]:
    if path is None:
        text = _DEFAULT_POLICY_TEXT
    else:
        text = Path(path).read_text(encoding="utf-8")
    return yaml.safe_load(text) or {}


def evaluate(summary_path: Path, policy_path: Path | None = None) -> list[str]:
    summary = _load_summary(summary_path)
    policy = _load_policy(policy_path)

    errors: list[str] = []

    min_success = policy.get("min_success_rate")
    if min_success is not None:
        rate = summary.get("success_rate")
        if isinstance(rate, (int, float)) and rate < float(min_success):
            errors.append(f"success_rate {rate:.3f} < min {float(min_success):.3f}")

    max_latency = policy.get("max_avg_latency_ms")
    if max_latency is not None:
        avg_latency = summary.get("avg_latency_ms")
        if isinstance(avg_latency, (int, float)) and avg_latency > float(max_latency):
            errors.append(
                f"avg_latency_ms {float(avg_latency):.1f} > max {float(max_latency):.1f}"
            )

    per_step = policy.get("per_step", {})
    default_step_policy = per_step.get("default", {})

    steps = summary.get("steps", [])
    for step in steps:
        if not isinstance(step, dict):
            continue
        name = str(step.get("name", "<unknown>"))
        step_policy = per_step.get(name, default_step_policy)

        runs = step.get("runs")
        successes = step.get("successes")
        error_rate = _ratio((runs or 0) - (successes or 0), runs)
        max_error_rate = step_policy.get("max_error_rate")
        if (
            error_rate is not None
            and max_error_rate is not None
            and error_rate > float(max_error_rate)
        ):
            errors.append(
                f"step {name}: error_rate {error_rate:.3f} > max {float(max_error_rate):.3f}"
            )

        step_latency = step.get("avg_latency_ms")
        max_step_latency = step_policy.get("max_avg_latency_ms")
        if (
            isinstance(step_latency, (int, float))
            and max_step_latency is not None
            and step_latency > float(max_step_latency)
        ):
            errors.append(
                f"step {name}: avg_latency_ms {float(step_latency):.1f} > max {float(max_step_latency):.1f}"
            )

        model = None
        if isinstance(step.get("models"), list) and step["models"]:
            model = step["models"][0]
        elif isinstance(step.get("model"), str):
            model = step["model"]

        model_policy = policy.get("models", {})
        denylist = model_policy.get("denylist", [])
        allowlist = model_policy.get("allowlist", [])
        if model:
            if any(_match_pattern(model, pattern) for pattern in denylist):
                errors.append(f"step {name}: model '{model}' is denied")
            if allowlist and not any(_match_pattern(model, pattern) for pattern in allowlist):
                errors.append(f"step {name}: model '{model}' not allowed")

        step_mcp = step.get("mcp", {})
        step_mcp_calls = step_mcp.get("calls")
        step_mcp_errors = step_mcp.get("errors")
        step_mcp_rate = _ratio(step_mcp_errors, step_mcp_calls)
        max_step_mcp_rate = step_policy.get("max_mcp_error_rate")
        if (
            step_mcp_rate is not None
            and max_step_mcp_rate is not None
            and step_mcp_rate > float(max_step_mcp_rate)
        ):
            errors.append(
                f"step {name}: mcp.error_rate {step_mcp_rate:.3f} > max {float(max_step_mcp_rate):.3f}"
            )

    mcp_policy = policy.get("mcp", {})
    max_mcp_rate = mcp_policy.get("max_error_rate")
    if max_mcp_rate is not None:
        total_calls = summary.get("mcp", {}).get("calls")
        total_errors = summary.get("mcp", {}).get("errors")
        if total_calls is None:
            total_calls = sum((step.get("mcp", {}).get("calls") or 0) for step in steps)
        if total_errors is None:
            total_errors = sum((step.get("mcp", {}).get("errors") or 0) for step in steps)
        rate = _ratio(total_errors, total_calls)
        if rate is not None and rate > float(max_mcp_rate):
            errors.append(f"mcp.error_rate {rate:.3f} > max {float(max_mcp_rate):.3f}")

    return errors
