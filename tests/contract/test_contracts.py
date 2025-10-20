import json
import pathlib

import jsonschema

base = pathlib.Path("contracts")


def load(name: str) -> dict:
    return json.loads((base / name).read_text())


def test_candidate_profile_schema_valid() -> None:
    jsonschema.Draft7Validator.check_schema(load("candidate_profile.json"))


def test_offer_packet_schema_valid() -> None:
    jsonschema.Draft7Validator.check_schema(load("offer_packet.json"))


def test_salary_band_schema_valid() -> None:
    jsonschema.Draft7Validator.check_schema(load("salary_band.json"))
