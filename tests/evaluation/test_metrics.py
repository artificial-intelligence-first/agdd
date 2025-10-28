"""Unit tests for compensation validator metrics"""

from __future__ import annotations

import sys
from pathlib import Path

# Add catalog to path for imports
catalog_path = Path(__file__).parents[2] / "catalog" / "evals" / "compensation-validator" / "metric"
spec_path = catalog_path / "validator.py"

import importlib.util
spec = importlib.util.spec_from_file_location("validator", spec_path)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load validator module from {spec_path}")
validator_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator_module)

salary_range_check = validator_module.salary_range_check
consistency_check = validator_module.consistency_check
completeness_check = validator_module.completeness_check


def test_salary_range_check_valid():
    """Test salary range check with valid salary"""
    payload = {"offer": {"base_salary": 150000, "currency": "USD"}}
    context = {}

    result = salary_range_check(payload, context)

    assert result["score"] == 1.0
    assert result["passed"] is True
    assert result["details"]["within_range"] is True


def test_salary_range_check_too_low():
    """Test salary range check with too low salary"""
    payload = {"offer": {"base_salary": 10000, "currency": "USD"}}
    context = {}

    result = salary_range_check(payload, context)

    assert result["score"] < 1.0
    assert result["passed"] is False
    assert result["details"]["within_range"] is False


def test_salary_range_check_too_high():
    """Test salary range check with excessively high salary"""
    payload = {"offer": {"base_salary": 1000000, "currency": "USD"}}
    context = {}

    result = salary_range_check(payload, context)

    assert result["score"] < 1.0
    assert result["passed"] is False
    assert result["details"]["within_range"] is False


def test_consistency_check_valid():
    """Test consistency check with valid offer"""
    payload = {
        "offer": {
            "base_salary": 150000,
            "bonus": 20000,
            "equity_value": 50000,
            "currency": "USD",
        }
    }
    context = {}

    result = consistency_check(payload, context)

    assert result["score"] >= 0.9
    assert result["passed"] is True
    assert len(result["details"]["issues"]) == 0


def test_consistency_check_high_equity():
    """Test consistency check with unusually high equity"""
    payload = {
        "offer": {
            "base_salary": 100000,
            "bonus": 0,
            "equity_value": 500000,  # 5x base salary
            "currency": "USD",
        }
    }
    context = {}

    result = consistency_check(payload, context)

    assert result["score"] < 1.0
    assert "equity_value_unusually_high" in result["details"]["issues"]


def test_consistency_check_negative_values():
    """Test consistency check with negative values"""
    payload = {
        "offer": {
            "base_salary": -100000,  # Invalid
            "bonus": 0,
            "equity_value": 0,
            "currency": "USD",
        }
    }
    context = {}

    result = consistency_check(payload, context)

    assert result["score"] <= 0.5  # Score is 0.5 after -0.5 penalty
    assert result["passed"] is False
    assert "negative_values_detected" in result["details"]["issues"]


def test_completeness_check_complete():
    """Test completeness check with all required fields"""
    payload = {
        "offer": {
            "base_salary": 150000,
            "currency": "USD",
            "role": "Senior Engineer",
            "level": "Senior",
            "bonus": 20000,
            "equity_value": 50000,
            "benefits": "Health, Dental",
            "start_date": "2025-01-01",
        }
    }
    context = {}

    result = completeness_check(payload, context)

    assert result["score"] == 1.0
    assert result["passed"] is True
    assert len(result["details"]["missing_required"]) == 0
    assert len(result["details"]["missing_recommended"]) == 0


def test_completeness_check_missing_required():
    """Test completeness check with missing required fields"""
    payload = {"offer": {"base_salary": 150000}}  # Missing: currency, role, level
    context = {}

    result = completeness_check(payload, context)

    assert result["passed"] is False
    assert "currency" in result["details"]["missing_required"]
    assert "role" in result["details"]["missing_required"]
    assert "level" in result["details"]["missing_required"]


def test_completeness_check_missing_recommended():
    """Test completeness check with missing recommended fields"""
    payload = {
        "offer": {
            "base_salary": 150000,
            "currency": "USD",
            "role": "Engineer",
            "level": "Mid",
            # Missing recommended: bonus, equity_value, benefits, start_date
        }
    }
    context = {}

    result = completeness_check(payload, context)

    assert result["passed"] is True  # Required fields are present
    assert result["score"] < 1.0  # Score reduced by missing recommended fields
    assert len(result["details"]["missing_recommended"]) > 0
