"""
Doc generation skill.

Constructs an offer packet from a candidate profile and optional compensation
context. Performs schema validation on input/output contracts.

MCP INTEGRATION STATUS:
    This skill performs local data transformation and does not currently require
    MCP integration. It operates synchronously on provided data.

    If future requirements include fetching external data (e.g., templates from
    filesystem MCP server or compensation data from database), this skill would
    need:
    - Conversion to async/await pattern
    - MCP client dependency injection
    - Declaration of MCP server dependencies in skill.yaml

CURRENT IMPLEMENTATION:
    - Synchronous execution
    - Schema validation using local contract files
    - Pure data transformation (no external I/O)
    - No async conversion planned unless external data sources are added
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[4]  # Point to repo root
INPUT_CONTRACT = ROOT / "catalog" / "contracts" / "candidate_profile.json"
OUTPUT_CONTRACT = ROOT / "catalog" / "contracts" / "offer_packet.json"


def _load_schema(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Schema at {path} must be a JSON object")
    return data


INPUT_SCHEMA = _load_schema(INPUT_CONTRACT)
OUTPUT_SCHEMA = _load_schema(OUTPUT_CONTRACT)


def _validate(payload: Dict[str, Any], schema: Dict[str, Any], name: str) -> None:
    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError as exc:  # pragma: no cover - defensive
        raise ValueError(f"{name} schema validation failed: {exc.message}") from exc


def _normalized_candidate(payload: Dict[str, Any]) -> Dict[str, Any]:
    identifier = str(payload.get("id", "")).strip()
    if not identifier:
        raise ValueError("Candidate profile requires an 'id' field")

    candidate = {
        "id": identifier,
        "name": payload.get("name") or "Unknown Candidate",
        "role": payload.get("role") or payload.get("title") or "Unknown Role",
        "level": payload.get("level") or payload.get("seniority"),
        "location": payload.get("location"),
    }
    return candidate


def _compensation_section(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_band = payload.get("salary_band")
    band = raw_band if isinstance(raw_band, dict) else {}
    base = payload.get("base_salary") or band.get("base") or band.get("min")
    maximum = payload.get("max_salary") or band.get("max")
    currency = band.get("currency") or "USD"
    components: Dict[str, Any] = {}
    if base is not None:
        components["base"] = {"amount": base, "currency": currency}
    if maximum is not None:
        components["ceiling"] = {"amount": maximum, "currency": currency}

    variable = payload.get("variable_comp")
    if variable:
        components["variable"] = variable

    equity = payload.get("equity")
    if equity:
        components["equity"] = equity

    recommendation = payload.get("compensation_recommendation")
    if recommendation:
        components["recommendation"] = recommendation

    source = payload.get("salary_band_source") or band.get("source")
    return {
        "components": components,
        "source": source,
    }


def _build_narrative(candidate: Dict[str, Any], compensation: Dict[str, Any]) -> Dict[str, str]:
    name = candidate.get("name") or candidate["id"]
    role = candidate.get("role") or "the target role"
    base_component = compensation["components"].get("base")
    if base_component:
        comp_phrase = f"a base salary of {base_component['amount']} {base_component['currency']}"
    else:
        comp_phrase = "a competitive base salary aligned with market data"

    highlights = [
        f"Recommend {comp_phrase} for {name} ({role}).",
        "Total compensation aligns with market benchmarks and advisor guidance.",
    ]

    if compensation.get("source"):
        highlights.append(f"Compensation source: {compensation['source']}.")

    return {
        "summary": " ".join(highlights),
        "talking_points": "\n".join(highlights),
    }


def _collect_warnings(payload: Dict[str, Any], compensation: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    if not compensation["components"]:
        warnings.append("Salary band information is missing; confirm compensation details.")
    if payload.get("advisor_notes") is None:
        warnings.append("Advisor notes not supplied.")
    if payload.get("salary_band") is None:
        warnings.append("Salary band lookup result not attached.")
    return warnings


def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a structured offer packet from a candidate profile.

    CURRENT IMPLEMENTATION: Pure synchronous data transformation.
    No external I/O or MCP integration required at this time.

    Args:
        payload: Candidate profile data matching the candidate_profile contract.

    Returns:
        Offer packet payload satisfying the offer_packet contract.

    NOTE: If future requirements include fetching offer templates from filesystem
    or querying compensation databases, convert to async and add mcp_client parameter.
    """
    _validate(payload, INPUT_SCHEMA, "candidate_profile")
    candidate = _normalized_candidate(payload)
    compensation = _compensation_section(payload)
    narrative = _build_narrative(candidate, compensation)
    warnings = _collect_warnings(payload, compensation)

    offer_id = payload.get("offer_id") or f"offer-{candidate['id']}"
    result: Dict[str, Any] = {
        "offer_id": str(offer_id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate": candidate,
        "compensation": compensation,
        "narrative": narrative,
        "warnings": warnings,
        "provenance": {
            "schemas": {
                "input": str(INPUT_CONTRACT),
                "output": str(OUTPUT_CONTRACT),
            },
            "inputs": ["candidate_profile"],
        },
    }

    _validate(result, OUTPUT_SCHEMA, "offer_packet")
    return result
