"""
Example Web Search MCP Tool

Demonstrates integration with the fetch MCP server for web content retrieval.
This example shows how to wrap an MCP tool for practical use cases, with
graceful fallback to mock data when MCP is unavailable.

MCP Integration Pattern:
- Attempts to use the fetch MCP server when MCPRuntime is provided
- Falls back to mock data if MCP is unavailable or fails
- Demonstrates async/await patterns for MCP tool execution
- Shows proper error handling and result extraction

Note: This is a simplified example. Production implementations should:
- Use proper MCP client libraries (shown here with MCPRuntime)
- Implement robust error handling (demonstrated with try/except)
- Add caching mechanisms
- Handle more content types
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import jsonschema
import yaml

# MCP integration imports
try:
    from agdd.mcp.runtime import MCPRuntime
except ImportError:
    # Graceful degradation if MCP runtime not available
    MCPRuntime = None  # type: ignore

logger = logging.getLogger(__name__)


def _find_repo_root(start_path: Path) -> Path:
    """
    Find repository root by looking for pyproject.toml or .git directory.

    This is more robust than using a fixed parent level, which can break
    when the skill is nested at different depths.

    Args:
        start_path: Starting path (typically __file__)

    Returns:
        Path to repository root

    Raises:
        RuntimeError: If repository root cannot be found
    """
    current = start_path.resolve()
    # Walk up the directory tree
    for parent in [current] + list(current.parents):
        # Check for repository markers
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent
    # Fallback: assume we're in catalog/skills/<name>/impl/ and go up 4 levels
    # This works for standard skill structure: impl -> skill -> skills -> catalog -> root
    return start_path.resolve().parents[4]


ROOT = _find_repo_root(Path(__file__))
INPUT_CONTRACT = ROOT / "catalog" / "contracts" / "web_search_query.schema.json"
OUTPUT_CONTRACT = ROOT / "catalog" / "contracts" / "web_search_result.schema.json"


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


async def _fetch_url_via_mcp(
    url: str,
    extract_text: bool = True,
    mcp: Optional[MCPRuntime] = None,
) -> Dict[str, Any]:
    """
    Fetch URL content using the fetch MCP server.

    Attempts to use the MCP runtime if provided, otherwise falls back to mock data.
    This demonstrates the recommended pattern for MCP integration with graceful degradation.

    Args:
        url: URL to fetch
        extract_text: Whether to extract text content from HTML
        mcp: Optional MCPRuntime instance for calling the fetch server

    Returns:
        Response from MCP server or mock data

    Raises:
        RuntimeError: If MCP server call fails critically
    """
    # Try to use real MCP if available
    if mcp is not None:
        try:
            logger.info(f"Attempting to fetch {url} via MCP fetch server")

            # Call the fetch MCP server's fetch_url tool
            result = await mcp.execute_tool(
                server_id="fetch", tool_name="fetch", arguments={"url": url}
            )

            # Check if MCP call succeeded
            if result.success and result.output:
                logger.info(f"Successfully fetched {url} via MCP")

                # Extract content from MCP result
                # The fetch server typically returns content in result.output
                # Format may vary, so we handle common patterns
                if isinstance(result.output, list):
                    # MCP often returns content as list of content blocks
                    content = ""
                    for item in result.output:
                        if isinstance(item, dict) and "text" in item:
                            content += item["text"]
                        elif isinstance(item, str):
                            content += item
                elif isinstance(result.output, dict):
                    content = result.output.get("content", str(result.output))
                else:
                    content = str(result.output)

                return {
                    "url": url,
                    "status_code": 200,
                    "content_type": result.metadata.get("content_type", "text/html"),
                    "content": content,
                    "title": result.metadata.get("title", ""),
                }
            else:
                # MCP call failed, log and fall through to mock
                logger.warning(
                    f"MCP fetch failed for {url}: {result.error}. Falling back to mock data."
                )
        except Exception as exc:
            # MCP call raised an exception, log and fall through to mock
            logger.warning(
                f"Exception during MCP fetch for {url}: {exc}. Falling back to mock data.",
                exc_info=True,
            )
    else:
        logger.info(f"No MCP runtime provided, using mock data for {url}")

    # Fallback: return mock data
    # This ensures the skill works even without MCP configured
    logger.debug(f"Returning mock data for {url}")
    return {
        "url": url,
        "status_code": 200,
        "content_type": "text/html",
        "content": f"Mock content from {url}. This is demonstration data used when MCP is not available.",
        "title": "Mock Title (MCP Not Available)",
    }


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


async def run(
    payload: Dict[str, Any],
    *,
    mcp: Optional[MCPRuntime] = None,
) -> Dict[str, Any]:
    """
    Execute web search/fetch operation with MCP integration.

    This async function demonstrates the recommended pattern for MCP-enabled skills:
    - Accepts optional MCPRuntime via keyword-only parameter
    - Passes MCP runtime to underlying async functions
    - Maintains backward compatibility (works without MCP)
    - Validates input/output contracts
    - Provides comprehensive error handling

    Args:
        payload: Input data with 'url' and optional 'extract_text' fields
        mcp: Optional MCPRuntime instance for calling MCP servers

    Returns:
        Output data with URL content and metadata

    Raises:
        ValueError: If input validation fails
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

    # Fetch content via MCP (or fallback to mock)
    try:
        mcp_response = await _fetch_url_via_mcp(url, extract_text, mcp=mcp)
    except Exception as exc:
        # Fallback: return error result
        logger.error(f"Fetch failed for {url}: {exc}", exc_info=True)
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
