"""
Example Web Search MCP Tool

Demonstrates integration with the fetch MCP server for web content retrieval.
This example shows how to wrap an MCP tool for practical use cases.

Note: This is a simplified example. Production implementations should:
- Use proper MCP client libraries
- Implement robust error handling
- Add caching mechanisms
- Handle more content types
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[4]
INPUT_CONTRACT = ROOT / "catalog" / "contracts" / "web_search_query.json"
OUTPUT_CONTRACT = ROOT / "catalog" / "contracts" / "web_search_result.json"


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
    if not path.exists():
        # Return minimal schema if contract doesn't exist yet
        return {"type": "object"}

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


def _validate_url(url: str) -> None:
    """
    Basic URL validation.

    Args:
        url: URL string to validate

    Raises:
        ValueError: If URL is invalid
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")

    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")


def _fetch_url_via_mcp(url: str, extract_text: bool = True) -> Dict[str, Any]:
    """
    Fetch URL content using the fetch MCP server.

    This is a simplified example using subprocess to call npx.
    Production code should use proper MCP client libraries.

    Args:
        url: URL to fetch
        extract_text: Whether to extract text content from HTML

    Returns:
        Response from MCP server

    Raises:
        RuntimeError: If MCP server call fails
    """
    # Example implementation using subprocess
    # In production, use a proper MCP client library
    try:
        # This is a placeholder - actual MCP invocation would be different
        # For demonstration purposes, we'll use a mock response
        return {
            "url": url,
            "status_code": 200,
            "content_type": "text/html",
            "content": f"Mock content from {url}",
            "title": "Mock Title",
        }
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"MCP fetch failed: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Unexpected error during fetch: {exc}") from exc


def _extract_text_content(html_content: str) -> str:
    """
    Extract plain text from HTML content.

    This is a simplified implementation. Production code should use
    proper HTML parsing libraries like BeautifulSoup or lxml.

    Args:
        html_content: Raw HTML content

    Returns:
        Extracted text content
    """
    # Simplified text extraction
    # In production, use BeautifulSoup or similar
    import re

    # Remove script and style elements
    text = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Clean up whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute web search/fetch operation.

    Args:
        payload: Input data with 'url' and optional 'extract_text' fields

    Returns:
        Output data with URL content and metadata

    Raises:
        ValueError: If input validation fails
        RuntimeError: If fetch operation fails
    """
    # Validate input
    _validate(payload, INPUT_SCHEMA, "web_search_query")

    # Extract parameters
    url = payload.get("url")
    if not url:
        raise ValueError("Missing required field: url")

    extract_text = payload.get("extract_text", True)

    # Validate URL
    _validate_url(url)

    # Fetch content via MCP
    try:
        mcp_response = _fetch_url_via_mcp(url, extract_text)
    except Exception as exc:
        # Fallback: return error result
        return {
            "url": url,
            "success": False,
            "error": str(exc),
            "metadata": {"status_code": 0, "content_type": ""},
        }

    # Process response
    content = mcp_response.get("content", "")
    if extract_text and mcp_response.get("content_type", "").startswith("text/html"):
        content = _extract_text_content(content)

    result: Dict[str, Any] = {
        "url": url,
        "success": True,
        "title": mcp_response.get("title", ""),
        "content": content,
        "metadata": {
            "status_code": mcp_response.get("status_code", 200),
            "content_type": mcp_response.get("content_type", ""),
            "extracted_text": extract_text,
        },
    }

    # Validate output
    _validate(result, OUTPUT_SCHEMA, "web_search_result")

    return result
