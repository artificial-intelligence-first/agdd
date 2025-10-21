from __future__ import annotations

import json
from importlib import resources

from jsonschema import Draft202012Validator


def _load_schema() -> dict:
    resource = resources.files("agdd.assets.contracts").joinpath("agent.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def test_agent_schema_is_valid() -> None:
    """Verify agent.schema.json is a valid JSON Schema"""
    Draft202012Validator.check_schema(_load_schema())
