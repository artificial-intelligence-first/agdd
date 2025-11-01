"""Skill system for the MAGSAG framework.

This module provides the skill registry and base protocols for skill development.

Skills are the executable components that perform specific tasks in the MAGSAG
framework. Modern skills are asynchronous with MCP integration.

**Modern Skills**: Asynchronous skills with MCP integration
- Use the `MCPSkill` protocol
- Support structured payloads (dict[str, Any])
- Access to MCPRuntime for external tools and services
- Enhanced validation and error handling via `SkillBase`

Base Classes and Protocols:
    - MCPSkill: Protocol for asynchronous skills with MCP support
    - SkillBase: Helper class with validation and MCP utilities

Example:
    ```python
    from magsag.skills.base import MCPSkill, SkillBase
    from magsag.mcp import MCPRuntime, MCPRegistry

    class DatabaseSkill:
        async def execute(
            self,
            payload: dict[str, Any],
            mcp_runtime: MCPRuntime
        ) -> dict[str, Any]:
            SkillBase.validate_payload(payload, input_schema)
            result = await mcp_runtime.query_postgres(
                server_id="pg-readonly",
                sql=payload["query"]
            )
            return {"rows": result.output}
    ```
"""

from __future__ import annotations

# Import base protocols and helpers
from magsag.skills.base import (
    MCPSkill,
    SkillBase,
    SkillMCPError,
    SkillValidationError,
)

__all__ = [
    # Protocols
    "MCPSkill",
    # Helper class
    "SkillBase",
    # Exceptions
    "SkillValidationError",
    "SkillMCPError",
]
