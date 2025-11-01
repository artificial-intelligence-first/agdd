"""
Utilities for serializing storage payloads into JSON-safe structures.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


def json_safe(value: Any) -> Any:
    """
    Convert arbitrary Python objects into JSON-serializable structures.

    Recursively normalizes unsupported types (datetime, set, bytes, Path, etc.)
    so they can be safely passed to json.dumps or database JSON columns.
    """
    if isinstance(value, dict):
        return {str(key): json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [json_safe(item) for item in value]
    if isinstance(value, datetime):
        ts = value if value.tzinfo else value.replace(tzinfo=UTC)
        return ts.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC).isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        # Support Pydantic models and similar dataclasses
        try:
            dumped = value.model_dump()
            return json_safe(dumped)
        except Exception:  # pragma: no cover - fallback to str if model_dump fails
            return str(value)
    if hasattr(value, "__dict__") and not isinstance(value, type):
        try:
            return json_safe(vars(value))
        except Exception:  # pragma: no cover - fallback to str
            return str(value)
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value

    return str(value)


__all__ = ["json_safe"]
