from __future__ import annotations

import json
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator


def _load_schema() -> dict[str, Any]:
    resource = resources.files("agdd.assets.contracts").joinpath("agent.schema.json")
    data = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("agent.schema.json must contain a JSON object schema")
    return data


def test_agent_schema_is_valid() -> None:
    """Verify agent.schema.json is a valid JSON Schema"""
    Draft202012Validator.check_schema(_load_schema())
