from __future__ import annotations

import json
import pathlib
from importlib import resources

import yaml
from jsonschema import Draft202012Validator

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELLO_AGENT_PATH = ROOT / "registry" / "agents" / "hello.yaml"


def _load_schema() -> dict:
    resource = resources.files("agdd.assets.contracts").joinpath("agent.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def test_agent_schema_is_valid() -> None:
    Draft202012Validator.check_schema(_load_schema())


def test_hello_agent_descriptor_matches_schema() -> None:
    schema = _load_schema()
    descriptor = yaml.safe_load(HELLO_AGENT_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(descriptor)
