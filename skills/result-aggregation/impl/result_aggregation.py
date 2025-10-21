"""
Result Aggregation Skill

Aggregates sub-agent results into unified output.
"""

from typing import Any, Dict, List


def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggregate results from multiple sub-agents.

    Args:
        payload: Dict with 'results' key containing list of sub-agent outputs

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
    aggregated = {}
    for result in results:
        aggregated.update(result)

    return aggregated
