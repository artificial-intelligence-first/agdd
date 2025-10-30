"""
Compensation Validator Metrics

Implements quality, safety, and consistency checks for compensation offers.
"""

from __future__ import annotations

from typing import Any, Dict


def salary_range_check(payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates that salary is within expected range.

    Args:
        payload: SAG output containing compensation offer
        context: Execution context (agent_id, run_id, etc.)

    Returns:
        {
            "score": float (0.0-1.0),
            "passed": bool,
            "details": {...}
        }
    """
    offer = payload.get("offer", {})

    # Extract base_salary from nested structure (comp_advisor_output.schema.json)
    base_salary_obj = offer.get("base_salary", {})
    if isinstance(base_salary_obj, dict):
        base_salary = base_salary_obj.get("amount", 0)
        currency = base_salary_obj.get("currency", "USD")
    else:
        # Fallback for flat structure (backwards compatibility)
        base_salary = base_salary_obj if isinstance(base_salary_obj, (int, float)) else 0
        currency = offer.get("currency", "USD")

    # Define reasonable ranges by currency
    salary_ranges = {
        "USD": {"min": 30000, "max": 500000},
        "EUR": {"min": 25000, "max": 400000},
        "GBP": {"min": 20000, "max": 350000},
        "JPY": {"min": 3000000, "max": 50000000},
    }

    # Default range if currency not recognized
    expected = salary_ranges.get(currency, {"min": 0, "max": 1000000})

    # Check if within range
    within_range = expected["min"] <= base_salary <= expected["max"]

    # Calculate score (1.0 if within range, degrade based on deviation)
    if within_range:
        score = 1.0
    else:
        if base_salary < expected["min"]:
            deviation = (expected["min"] - base_salary) / expected["min"]
        else:
            deviation = (base_salary - expected["max"]) / expected["max"]
        score = max(0.0, 1.0 - deviation)

    return {
        "score": score,
        "passed": within_range,
        "details": {
            "base_salary": base_salary,
            "currency": currency,
            "expected_range": expected,
            "within_range": within_range,
        },
    }


def consistency_check(payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Checks for internal consistency in compensation package.

    Validates that:
    - Total compensation >= base salary
    - Equity value is reasonable relative to base
    - All monetary values use same currency
    - Sign-on bonus is reasonable

    Args:
        payload: SAG output containing compensation offer
        context: Execution context

    Returns:
        Evaluation result with score and details
    """
    offer = payload.get("offer", {})

    # Extract values from nested structure (comp_advisor_output.schema.json)
    base_salary_obj = offer.get("base_salary", {})
    if isinstance(base_salary_obj, dict):
        base_salary = base_salary_obj.get("amount", 0)
        currency = base_salary_obj.get("currency", "USD")
    else:
        base_salary = base_salary_obj if isinstance(base_salary_obj, (int, float)) else 0
        currency = offer.get("currency", "USD")

    # Extract sign-on bonus
    sign_on_obj = offer.get("sign_on_bonus", {})
    if isinstance(sign_on_obj, dict):
        bonus = sign_on_obj.get("amount", 0)
        bonus_currency = sign_on_obj.get("currency", currency)
    else:
        bonus = offer.get("bonus", 0)
        bonus_currency = currency

    # Extract equity value
    equity_obj = offer.get("equity", {})
    if isinstance(equity_obj, dict):
        equity_value = equity_obj.get("amount", 0)
    else:
        equity_value = offer.get("equity_value", 0)

    issues = []
    score = 1.0

    # Check 1: Currency consistency
    if bonus > 0 and bonus_currency != currency:
        issues.append("currency_mismatch")
        score -= 0.2

    # Check 2: Total compensation >= base salary
    total_comp = base_salary + bonus + equity_value
    if total_comp < base_salary:
        issues.append("total_compensation_less_than_base")
        score -= 0.3

    # Check 3: Equity value is reasonable (typically 0-200% of base)
    if equity_value > 0:
        equity_ratio = equity_value / base_salary if base_salary > 0 else 0
        if equity_ratio > 2.0:
            issues.append("equity_value_unusually_high")
            score -= 0.2

    # Check 4: Sign-on bonus is reasonable (typically 0-100% of base)
    if bonus > 0:
        bonus_ratio = bonus / base_salary if base_salary > 0 else 0
        if bonus_ratio > 1.0:
            issues.append("sign_on_bonus_unusually_high")
            score -= 0.2

    # Check 5: All positive values
    if base_salary < 0 or bonus < 0 or equity_value < 0:
        issues.append("negative_values_detected")
        score -= 0.5

    score = max(0.0, score)
    passed = score >= 0.9

    return {
        "score": score,
        "passed": passed,
        "details": {
            "total_compensation": total_comp,
            "base_salary": base_salary,
            "sign_on_bonus": bonus,
            "equity_value": equity_value,
            "currency": currency,
            "issues": issues,
        },
    }


def completeness_check(payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensures all required fields are present in the offer.

    Args:
        payload: SAG output containing compensation offer
        context: Execution context

    Returns:
        Evaluation result with score and details
    """
    offer = payload.get("offer", {})

    # Required fields based on comp_advisor_output.schema.json
    required_fields = [
        "role",
        "base_salary",
        "band",
    ]

    # Optional but recommended fields
    recommended_fields = [
        "sign_on_bonus",
        "equity",
        "notes",
    ]

    missing_required = []
    missing_recommended = []

    # Check required fields
    for field in required_fields:
        value = offer.get(field)
        if value is None or value == "":
            missing_required.append(field)
        # For nested objects, check if they have required subfields
        elif field == "base_salary" and isinstance(value, dict):
            if "currency" not in value or "amount" not in value:
                missing_required.append(f"{field}.currency or {field}.amount")
        elif field == "band" and isinstance(value, dict):
            if "currency" not in value or "min" not in value or "max" not in value:
                missing_required.append(f"{field}.required_fields")

    # Check recommended fields
    for field in recommended_fields:
        if field not in offer or offer[field] is None or offer[field] == "":
            missing_recommended.append(field)

    # Calculate score
    required_score = (
        1.0 - (len(missing_required) / len(required_fields)) if required_fields else 1.0
    )
    recommended_score = (
        1.0 - (len(missing_recommended) / len(recommended_fields)) if recommended_fields else 1.0
    )

    # Weighted score: required=80%, recommended=20%
    score = (required_score * 0.8) + (recommended_score * 0.2)
    passed = len(missing_required) == 0

    return {
        "score": score,
        "passed": passed,
        "details": {
            "missing_required": missing_required,
            "missing_recommended": missing_recommended,
            "required_fields": required_fields,
            "recommended_fields": recommended_fields,
        },
    }


# Metric registry for dynamic lookup
METRICS = {
    "salary_range_check": salary_range_check,
    "consistency_check": consistency_check,
    "completeness_check": completeness_check,
}
