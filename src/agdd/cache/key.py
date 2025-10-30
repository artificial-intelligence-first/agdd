"""Semantic cache key normalization utilities.

This module provides functions for generating stable, canonical cache keys
from various input data structures. The normalization ensures that semantically
equivalent inputs produce identical keys regardless of ordering or formatting.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def normalize_input(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize a dictionary to ensure stable ordering.

    Recursively sorts all dictionary keys and list items containing dictionaries
    to ensure consistent ordering for cache key generation.

    Args:
        data: Input dictionary to normalize.

    Returns:
        A new dictionary with all keys sorted recursively.

    Example:
        >>> normalize_input({"b": 1, "a": 2})
        {'a': 2, 'b': 1}
    """
    if isinstance(data, dict):
        return {k: normalize_input(v) for k, v in sorted(data.items())}
    elif isinstance(data, list):
        return [normalize_input(item) for item in data]
    else:
        return data


def hash_stable(data: Any) -> str:
    """Generate a stable hash from any JSON-serializable data.

    Creates a SHA-256 hash from the JSON representation of the input data,
    ensuring consistent ordering through sort_keys=True.

    Args:
        data: Any JSON-serializable data structure.

    Returns:
        A hexadecimal SHA-256 hash string.

    Example:
        >>> hash_stable({"tool": "test", "id": 1})
        'a1b2c3d4...'
    """
    stable_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(stable_json.encode("utf-8")).hexdigest()


def compute_key(
    template_id: str,
    tool_specs: list[dict[str, Any]],
    schema: dict[str, Any],
    caps: dict[str, Any],
) -> str:
    """Compute a canonical cache key from template components.

    Generates a stable cache key by normalizing and hashing the input components.
    The key is deterministic and will be identical for semantically equivalent
    inputs regardless of their ordering.

    Args:
        template_id: Identifier for the template or prompt.
        tool_specs: List of tool specification dictionaries.
        schema: Schema definition dictionary.
        caps: Capabilities configuration dictionary.

    Returns:
        A hexadecimal SHA-256 hash string representing the canonical key.

    Example:
        >>> compute_key(
        ...     "template_v1",
        ...     [{"name": "tool_a"}, {"name": "tool_b"}],
        ...     {"type": "object"},
        ...     {"streaming": True}
        ... )
        'e4d909c3...'
    """
    # Sort tool specs by name for stability
    sorted_tools = sorted(tool_specs, key=lambda x: x.get("name", ""))

    # Create normalized composite structure
    normalized = {
        "template": template_id,
        "tools": normalize_input(sorted_tools),
        "schema": normalize_input(schema),
        "capabilities": normalize_input(caps),
    }

    return hash_stable(normalized)
