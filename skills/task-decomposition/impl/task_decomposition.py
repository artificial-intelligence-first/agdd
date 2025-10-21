"""
Task Decomposition Skill

Decomposes high-level requests into sub-agent tasks.
"""

from typing import Any, Dict, List


def run(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Decompose task into sub-agent delegations.

    Args:
        payload: Request payload (typically containing candidate_profile)

    Returns:
        List of task objects with sag_id and input
    """
    # Simple implementation: single task to compensation advisor
    # Production version would analyze complexity and create multiple tasks

    # Normalize input
    if "candidate_profile" in payload:
        profile = payload["candidate_profile"]
    else:
        profile = payload

    # For offer generation, we need compensation analysis
    tasks = [{"sag_id": "compensation-advisor-sag", "input": {"candidate_profile": profile}}]

    return tasks
