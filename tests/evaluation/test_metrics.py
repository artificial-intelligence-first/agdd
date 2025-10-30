"""Unit tests for compensation validator metrics"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

# Add catalog to path for imports
catalog_path = Path(__file__).parents[2] / "catalog" / "evals" / "compensation-validator" / "metric"
spec_path = catalog_path / "validator.py"
spec = importlib.util.spec_from_file_location("validator", spec_path)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load validator module from {spec_path}")
validator_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator_module)

salary_range_check = validator_module.salary_range_check
consistency_check = validator_module.consistency_check
completeness_check = validator_module.completeness_check


def test_salary_range_check_valid() -> None:
    """Test salary range check with valid salary (nested structure)"""
    payload: dict[str, Any] = {"offer": {"base_salary": {"currency": "USD", "amount": 150000}}}
    context: dict[str, Any] = {}

    result = salary_range_check(payload, context)

    assert result["score"] == 1.0
    assert result["passed"] is True
    assert result["details"]["within_range"] is True


def test_salary_range_check_too_low() -> None:
    """Test salary range check with too low salary (nested structure)"""
    payload: dict[str, Any] = {"offer": {"base_salary": {"currency": "USD", "amount": 10000}}}
    context: dict[str, Any] = {}

    result = salary_range_check(payload, context)

    assert result["score"] < 1.0
    assert result["passed"] is False
    assert result["details"]["within_range"] is False


def test_salary_range_check_too_high() -> None:
    """Test salary range check with excessively high salary (nested structure)"""
    payload: dict[str, Any] = {"offer": {"base_salary": {"currency": "USD", "amount": 1000000}}}
    context: dict[str, Any] = {}

    result = salary_range_check(payload, context)

    assert result["score"] < 1.0
    assert result["passed"] is False
    assert result["details"]["within_range"] is False


def test_consistency_check_valid() -> None:
    """Test consistency check with valid offer (nested structure)"""
    payload: dict[str, Any] = {
        "offer": {
            "base_salary": {"currency": "USD", "amount": 150000},
            "sign_on_bonus": {"currency": "USD", "amount": 20000},
            "equity": {"amount": 50000},
        }
    }
    context: dict[str, Any] = {}

    result = consistency_check(payload, context)

    assert result["score"] >= 0.9
    assert result["passed"] is True
    assert len(result["details"]["issues"]) == 0


def test_consistency_check_high_equity() -> None:
    """Test consistency check with unusually high equity (nested structure)"""
    payload: dict[str, Any] = {
        "offer": {
            "base_salary": {"currency": "USD", "amount": 100000},
            "sign_on_bonus": {"currency": "USD", "amount": 0},
            "equity": {"amount": 500000},  # 5x base salary
        }
    }
    context: dict[str, Any] = {}

    result = consistency_check(payload, context)

    assert result["score"] < 1.0
    assert "equity_value_unusually_high" in result["details"]["issues"]


def test_consistency_check_negative_values() -> None:
    """Test consistency check with negative values (nested structure)"""
    payload: dict[str, Any] = {
        "offer": {
            "base_salary": {"currency": "USD", "amount": -100000},  # Invalid
            "sign_on_bonus": {"currency": "USD", "amount": 0},
            "equity": {"amount": 0},
        }
    }
    context: dict[str, Any] = {}

    result = consistency_check(payload, context)

    assert result["score"] <= 0.5  # Score is 0.5 after -0.5 penalty
    assert result["passed"] is False
    assert "negative_values_detected" in result["details"]["issues"]


def test_completeness_check_complete() -> None:
    """Test completeness check with all required fields (nested structure)"""
    payload: dict[str, Any] = {
        "offer": {
            "role": "Senior Engineer",
            "base_salary": {"currency": "USD", "amount": 150000},
            "band": {"currency": "USD", "min": 100000, "max": 200000, "source": "internal"},
            "sign_on_bonus": {"currency": "USD", "amount": 20000},
            "equity": {"type": "RSU", "amount": 50000, "vesting_years": 4},
            "notes": "Competitive offer",
        }
    }
    context: dict[str, Any] = {}

    result = completeness_check(payload, context)

    assert result["score"] == 1.0
    assert result["passed"] is True
    assert len(result["details"]["missing_required"]) == 0
    assert len(result["details"]["missing_recommended"]) == 0


def test_completeness_check_missing_required() -> None:
    """Test completeness check with missing required fields (nested structure)"""
    payload: dict[str, Any] = {
        "offer": {
            "base_salary": {"currency": "USD", "amount": 150000}
            # Missing: role, band
        }
    }
    context: dict[str, Any] = {}

    result = completeness_check(payload, context)

    assert result["passed"] is False
    assert "role" in result["details"]["missing_required"]
    assert "band" in result["details"]["missing_required"]


def test_completeness_check_missing_recommended() -> None:
    """Test completeness check with missing recommended fields (nested structure)"""
    payload: dict[str, Any] = {
        "offer": {
            "role": "Engineer",
            "base_salary": {"currency": "USD", "amount": 150000},
            "band": {"currency": "USD", "min": 100000, "max": 200000},
            # Missing recommended: sign_on_bonus, equity, notes
        }
    }
    context: dict[str, Any] = {}

    result = completeness_check(payload, context)

    assert result["passed"] is True  # Required fields are present
    assert result["score"] < 1.0  # Score reduced by missing recommended fields
    assert len(result["details"]["missing_recommended"]) > 0


def test_backward_compatibility_flat_structure() -> None:
    """Test backward compatibility with flat structure"""
    # Old flat structure should still work
    payload: dict[str, Any] = {"offer": {"base_salary": 150000, "currency": "USD"}}
    context: dict[str, Any] = {}

    result = salary_range_check(payload, context)

    assert result["score"] == 1.0
    assert result["passed"] is True
