"""Skill system for the AGDD framework.

This module provides the skill registry and base protocols for skill development.

Skills are the executable components that perform specific tasks in the AGDD
framework. There are two generations of skills:

**Phase 1 (Legacy)**: Simple synchronous text-in/text-out skills
- Use the `Skill` protocol
- Registered in `_SKILL_FACTORIES` for backward compatibility
- Example: Echo skill

**Phase 2+ (Modern)**: Asynchronous skills with MCP integration
- Use the `MCPSkill` protocol
- Support structured payloads (dict[str, Any])
- Access to MCPRuntime for external tools and services
- Enhanced validation and error handling via `SkillBase`

Available Skills:
    To list all registered Phase 1 skills, use `available_skills()`.
    To get a specific Phase 1 skill instance, use `get_skill(name)`.

Base Classes and Protocols:
    - Skill: Protocol for Phase 1 legacy synchronous skills
    - MCPSkill: Protocol for Phase 2+ asynchronous skills with MCP support
    - SkillBase: Helper class with validation and MCP utilities

Example (Phase 1):
    ```python
    from agdd.skills import get_skill

    echo = get_skill("echo")
    result = echo("Hello, World!")
    ```

Example (Phase 2+):
    ```python
    from agdd.skills.base import MCPSkill, SkillBase
    from agdd.mcp import MCPRuntime, MCPRegistry

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

from typing import Callable, Dict, Iterable

# Import base protocols and helpers
from agdd.skills.base import (
    MCPSkill,
    Skill,
    SkillBase,
    SkillMCPError,
    SkillValidationError,
)

# Import legacy skills for backward compatibility
from agdd.skills.echo import Echo

SkillFactory = Callable[[], Skill]


# Legacy Phase 1 skill registry
# This maintains backward compatibility with the walking skeleton
_SKILL_FACTORIES: Dict[str, SkillFactory] = {
    "echo": Echo,
}


def available_skills() -> Iterable[str]:
    """Return the identifiers of registered Phase 1 skills.

    Returns:
        Iterable of skill names available in the legacy registry

    Note:
        This only includes Phase 1 synchronous skills.
        Phase 2+ MCPSkill implementations are not included here
        as they use a different instantiation pattern.
    """
    return _SKILL_FACTORIES.keys()


def get_skill(name: str) -> Skill:
    """Instantiate a registered Phase 1 skill by name.

    Args:
        name: Skill identifier (e.g., "echo")

    Returns:
        Instantiated skill implementing the Skill protocol

    Raises:
        KeyError: If skill name is not found in registry

    Example:
        ```python
        echo = get_skill("echo")
        result = echo("Hello, World!")
        ```
    """
    try:
        factory = _SKILL_FACTORIES[name]
    except KeyError as exc:  # pragma: no cover - tiny helper
        raise KeyError(name) from exc
    return factory()


__all__ = [
    # Protocols
    "Skill",
    "MCPSkill",
    # Helper class
    "SkillBase",
    # Exceptions
    "SkillValidationError",
    "SkillMCPError",
    # Legacy registry
    "SkillFactory",
    "available_skills",
    "get_skill",
]
