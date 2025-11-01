"""Unit tests for evaluation runtime"""

from __future__ import annotations

import pytest
from pathlib import Path
from typing import Any

from magsag.evaluation.runtime import EvalRuntime
from magsag.registry import Registry


@pytest.fixture
def eval_runtime() -> EvalRuntime:
    """Create EvalRuntime with test registry"""
    base_path = Path(__file__).parents[2]  # tests/ -> magsag/
    registry = Registry(base_path=base_path)
    return EvalRuntime(registry=registry)


def test_load_evaluator(eval_runtime: EvalRuntime) -> None:
    """Test loading evaluator descriptor"""
    eval_desc = eval_runtime.registry.load_eval("compensation-validator")

    assert eval_desc.slug == "compensation-validator"
    assert eval_desc.name == "CompensationValidator"
    assert eval_desc.hook_type == "post_eval"
    assert "compensation-advisor-sag" in eval_desc.target_agents
    assert len(eval_desc.metrics) == 3

    # Check metric configurations
    metric_ids = [m.id for m in eval_desc.metrics]
    assert "salary_range_check" in metric_ids
    assert "consistency_check" in metric_ids
    assert "completeness_check" in metric_ids


def test_list_evaluators(eval_runtime: EvalRuntime) -> None:
    """Test listing all available evaluators"""
    eval_slugs = eval_runtime.registry.list_evals()

    assert isinstance(eval_slugs, list)
    assert "compensation-validator" in eval_slugs


def test_get_evaluators_for_agent(eval_runtime: EvalRuntime) -> None:
    """Test getting evaluators for specific agent"""
    evals = eval_runtime.get_evaluators_for_agent("compensation-advisor-sag", "post_eval")

    assert len(evals) > 0
    assert any(e.slug == "compensation-validator" for e in evals)


def test_evaluate_valid_offer(eval_runtime: EvalRuntime) -> None:
    """Test evaluation with valid compensation offer"""
    payload: dict[str, Any] = {
        "offer": {
            "role": "Senior Engineer",
            "base_salary": {"currency": "USD", "amount": 150000},
            "band": {"currency": "USD", "min": 130000, "max": 180000},
            "sign_on_bonus": {"currency": "USD", "amount": 20000},
            "equity": {"amount": 50000},
            "notes": "Competitive offer with strong equity component",
        }
    }
    context: dict[str, Any] = {"agent_slug": "compensation-advisor-sag", "run_id": "test-123"}

    result = eval_runtime.evaluate("compensation-validator", payload, context)

    assert result.eval_slug == "compensation-validator"
    assert result.agent_slug == "compensation-advisor-sag"
    assert result.passed is True
    assert result.overall_score > 0.8
    assert len(result.metrics) == 3


def test_evaluate_invalid_salary_range(eval_runtime: EvalRuntime) -> None:
    """Test evaluation with out-of-range salary"""
    payload: dict[str, Any] = {
        "offer": {
            "role": "Engineer",
            "base_salary": {"currency": "USD", "amount": 10000},  # Too low
            "band": {"currency": "USD", "min": 30000, "max": 50000},
            "sign_on_bonus": {"currency": "USD", "amount": 0},
            "equity": {"amount": 0},
        }
    }
    context: dict[str, Any] = {"agent_slug": "compensation-advisor-sag"}

    result = eval_runtime.evaluate("compensation-validator", payload, context)

    # salary_range_check should fail
    salary_check = next((m for m in result.metrics if m.metric_id == "salary_range_check"), None)
    assert salary_check is not None
    assert salary_check.passed is False


def test_evaluate_missing_required_fields(eval_runtime: EvalRuntime) -> None:
    """Test evaluation with missing required fields"""
    payload: dict[str, Any] = {
        "offer": {
            "base_salary": {"currency": "USD", "amount": 150000},
            # Missing: role, band (required fields)
        }
    }
    context: dict[str, Any] = {"agent_slug": "compensation-advisor-sag"}

    result = eval_runtime.evaluate("compensation-validator", payload, context)

    # completeness_check should fail
    completeness = next((m for m in result.metrics if m.metric_id == "completeness_check"), None)
    assert completeness is not None
    assert completeness.passed is False

    # Overall evaluation should fail
    assert result.passed is False

    # Check that fail_open is False (fail-closed) for this evaluator
    assert result.fail_open is False


def test_evaluate_all_for_agent(eval_runtime: EvalRuntime) -> None:
    """Test running all evaluators for an agent"""
    payload: dict[str, Any] = {
        "offer": {
            "role": "Engineer",
            "base_salary": {"currency": "USD", "amount": 150000},
            "band": {"currency": "USD", "min": 120000, "max": 180000},
            "sign_on_bonus": {"currency": "USD", "amount": 10000},
            "equity": {"amount": 30000},
            "notes": "Standard offer",
        }
    }
    context: dict[str, Any] = {"agent_slug": "compensation-advisor-sag"}

    results = eval_runtime.evaluate_all("compensation-advisor-sag", "post_eval", payload, context)

    assert isinstance(results, list)
    assert len(results) > 0
    assert all(r.agent_slug == "compensation-advisor-sag" for r in results)
