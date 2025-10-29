from __future__ import annotations

"""
Result Aggregation Skill

Aggregates sub-agent results into unified output.
"""

from typing import Any, Optional

from agdd.mcp import MCPRuntime


async def run(
    payload: dict[str, Any],
    *,
    mcp: Optional[MCPRuntime] = None,
) -> dict[str, Any]:
    """
    Aggregate results from multiple sub-agents.

    Args:
        payload: Dict with 'results' key containing list of sub-agent outputs
        mcp: Optional MCP runtime. Not used in the default aggregation strategy.

    Returns:
        Aggregated output (typically offer packet format)
    """
    results = payload.get("results", [])

    # Simple aggregation: return first result
    # Production version would merge multiple results, resolve conflicts, etc.
    if not results:
        return {}

    # If single result, return it directly
    if len(results) == 1:
        return results[0]

    # Multiple results: merge strategy
    aggregated: dict[str, Any] = {}
    for result in results:
        aggregated.update(result)

    return aggregated
