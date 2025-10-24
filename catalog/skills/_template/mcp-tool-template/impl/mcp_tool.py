"""
MCP Tool Template

Template for creating skills that wrap Model Context Protocol (MCP) tools.
This provides a standardized structure for integrating external MCP servers
into the AGDD framework.

Usage:
    1. Copy this template to catalog/skills/<your-skill-name>/impl/mcp_tool.py
    2. Update the module docstring and class/function names
    3. Define your input/output contracts in catalog/contracts/
    4. Implement _call_mcp_tool() with your MCP tool invocation logic
    5. Update _prepare_request() and _process_response() for your use case
    6. Write tests in tests/test_mcp_tool.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import jsonschema
import yaml

# Update these paths to match your contract files
ROOT = Path(__file__).resolve().parents[3]
INPUT_CONTRACT = ROOT / "catalog" / "contracts" / "<input-contract>.json"
OUTPUT_CONTRACT = ROOT / "catalog" / "contracts" / "<output-contract>.json"


def _load_schema(path: Path) -> Dict[str, Any]:
    """
    Load and parse JSON Schema from a YAML or JSON file.

    Args:
        path: Path to the schema file

    Returns:
        Parsed schema as a dictionary

    Raises:
        ValueError: If the schema is not a valid JSON object
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Schema at {path} must be a JSON object")
    return data


INPUT_SCHEMA = _load_schema(INPUT_CONTRACT)
OUTPUT_SCHEMA = _load_schema(OUTPUT_CONTRACT)


def _validate(payload: Dict[str, Any], schema: Dict[str, Any], name: str) -> None:
    """
    Validate payload against JSON Schema.

    Args:
        payload: Data to validate
        schema: JSON Schema to validate against
        name: Human-readable name for error messages

    Raises:
        ValueError: If validation fails
    """
    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError as exc:
        raise ValueError(f"{name} schema validation failed: {exc.message}") from exc


def _prepare_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and transform input payload for MCP tool invocation.

    Args:
        payload: Validated input payload

    Returns:
        Dictionary of arguments to pass to the MCP tool

    TODO: Implement your request preparation logic here
    """
    # Example: Extract specific fields from payload
    # return {
    #     "query": payload.get("query", ""),
    #     "limit": payload.get("limit", 10),
    #     "filters": payload.get("filters", {}),
    # }
    return payload


def _call_mcp_tool(**kwargs: Any) -> Any:
    """
    Invoke the MCP tool via the configured server.

    Args:
        **kwargs: Arguments to pass to the MCP tool

    Returns:
        Raw response from the MCP tool

    Raises:
        RuntimeError: If the MCP tool invocation fails
        TimeoutError: If the MCP tool times out
        ValueError: If the MCP tool returns invalid data

    TODO: Implement your MCP tool invocation logic here.

    Example implementations:
    1. Direct subprocess call to npx:
        import subprocess
        result = subprocess.run(
            ["npx", "@modelcontextprotocol/server-<name>", "call-tool", ...],
            capture_output=True,
            check=True,
        )
        return json.loads(result.stdout)

    2. HTTP API call (if MCP server exposes HTTP):
        import requests
        response = requests.post("http://localhost:3000/tool", json=kwargs)
        response.raise_for_status()
        return response.json()

    3. Python MCP SDK (if available):
        from mcp_sdk import Client
        client = Client("server-id")
        return client.call_tool("tool-name", **kwargs)
    """
    raise NotImplementedError(
        "MCP tool invocation not implemented. "
        "Please implement _call_mcp_tool() for your specific MCP server."
    )


def _process_response(raw_response: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform MCP tool response to match output schema.

    Args:
        raw_response: Raw response from the MCP tool
        payload: Original input payload (for context)

    Returns:
        Transformed response matching the output schema

    TODO: Implement your response processing logic here
    """
    # Example: Extract and format response fields
    # return {
    #     "results": raw_response.get("items", []),
    #     "total_count": raw_response.get("total", 0),
    #     "metadata": {
    #         "source": "mcp-tool",
    #         "query": payload.get("query", ""),
    #     },
    # }
    return {"result": raw_response}


def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute the MCP tool with the given payload.

    This is the main entry point for the skill. It handles:
    - Input validation
    - Request preparation
    - MCP tool invocation
    - Response processing
    - Output validation

    Args:
        payload: Input data matching the input schema contract

    Returns:
        Output data matching the output schema contract

    Raises:
        ValueError: If input/output validation fails
        RuntimeError: If MCP tool invocation fails
    """
    # Validate input
    _validate(payload, INPUT_SCHEMA, "input")

    # Prepare request arguments
    request_args = _prepare_request(payload)

    # Call MCP tool
    try:
        raw_response = _call_mcp_tool(**request_args)
    except NotImplementedError:
        # Fallback for template: return mock data
        raw_response = {
            "status": "not_implemented",
            "message": "MCP tool invocation not implemented. Please implement _call_mcp_tool().",
        }
    except Exception as exc:
        # Handle MCP tool errors gracefully
        raise RuntimeError(f"MCP tool invocation failed: {exc}") from exc

    # Process response
    result = _process_response(raw_response, payload)

    # Validate output
    _validate(result, OUTPUT_SCHEMA, "output")

    return result
