"""Validate all contract JSON Schemas are well-formed"""
import json
import pathlib
from typing import Any

import jsonschema

base = pathlib.Path("contracts")


def load(name: str) -> dict[str, Any]:
    data = json.loads((base / name).read_text())
    if not isinstance(data, dict):
        raise AssertionError(f"{name} must contain a JSON object schema")
    return data


def test_candidate_profile_schema_valid() -> None:
    """Validate candidate_profile.schema.json is a valid JSON Schema"""
    jsonschema.Draft7Validator.check_schema(load("candidate_profile.schema.json"))


def test_comp_advisor_input_schema_valid() -> None:
    """Validate comp_advisor_input.schema.json is a valid JSON Schema"""
    jsonschema.Draft7Validator.check_schema(load("comp_advisor_input.schema.json"))


def test_comp_advisor_output_schema_valid() -> None:
    """Validate comp_advisor_output.schema.json is a valid JSON Schema"""
    jsonschema.Draft7Validator.check_schema(load("comp_advisor_output.schema.json"))


def test_offer_packet_schema_valid() -> None:
    """Validate offer_packet.schema.json is a valid JSON Schema"""
    jsonschema.Draft7Validator.check_schema(load("offer_packet.schema.json"))
