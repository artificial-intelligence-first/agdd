from __future__ import annotations

from typing import Any, Optional

from agdd.mcp import MCPRuntime

"""
Task Decomposition Skill

Decomposes high-level requests into sub-agent tasks.
"""


async def run(
    payload: dict[str, Any],
    *,
    mcp: Optional[MCPRuntime] = None,
) -> list[dict[str, Any]]:
    """
    Decompose task into sub-agent delegations.

    Args:
        payload: Request payload (typically containing candidate_profile)
        mcp: Optional MCP runtime. Not required for the current decomposition logic.

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
