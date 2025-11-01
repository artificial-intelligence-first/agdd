"""
Persona utilities for integrating agent personas into LLM prompts.

Provides helper functions to make persona content available to agents
during execution, particularly for LLM-based agents.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from magsag.registry import Registry


def build_system_prompt_with_persona(
    base_prompt: str,
    persona_content: Optional[str] = None,
    *,
    separator: str = "\n\n---\n\n",
) -> str:
    """
    Build a system prompt that includes persona content.

    Args:
        base_prompt: The base system prompt (task instructions, role definition, etc.)
        persona_content: Optional persona content from PERSONA.md
        separator: Separator between persona and base prompt

    Returns:
        Combined system prompt with persona (if provided) followed by base prompt

    Example:
        >>> from magsag.registry import Registry
        >>> from magsag.persona import build_system_prompt_with_persona
        >>>
        >>> registry = Registry()
        >>> agent = registry.load_agent("my-agent")
        >>>
        >>> system_prompt = build_system_prompt_with_persona(
        ...     base_prompt="You are a helpful assistant.",
        ...     persona_content=agent.persona_content
        ... )
        >>>
        >>> # Use system_prompt in LLM call
        >>> response = llm.generate(prompt=user_input, system=system_prompt)
    """
    if not persona_content:
        return base_prompt

    # Persona comes first, then the specific task instructions
    return f"{persona_content.strip()}{separator}{base_prompt.strip()}"


def get_agent_persona(agent_slug: str, registry: Optional[Registry] = None) -> Optional[str]:
    """
    Retrieve persona content for an agent by slug.

    Convenience function for agents to access persona content without
    explicitly loading the agent descriptor.

    Args:
        agent_slug: Agent slug (e.g., "offer-orchestrator-mag")
        registry: Optional Registry instance (uses global if not provided)

    Returns:
        Persona content string if available, None otherwise

    Example:
        >>> def run(payload, *, registry, skills, runner, obs):
        ...     from magsag.persona import get_agent_persona
        ...
        ...     # Get current agent's persona
        ...     persona = get_agent_persona("my-agent", registry=registry)
        ...
        ...     if persona:
        ...         system_prompt = build_system_prompt_with_persona(
        ...             base_prompt="Your task instructions here",
        ...             persona_content=persona
        ...         )
        ...     else:
        ...         system_prompt = "Your task instructions here"
    """
    if registry is None:
        from magsag.registry import get_registry

        registry = get_registry()

    agent = registry.load_agent(agent_slug)
    return agent.persona_content


def extract_persona_section(persona_content: str, section_name: str) -> Optional[str]:
    """
    Extract a specific section from persona content.

    Useful for extracting specific guidance (e.g., "Behavioral Guidelines",
    "Response Patterns") from structured PERSONA.md files.

    Args:
        persona_content: Full persona content from PERSONA.md
        section_name: Section heading to extract (e.g., "Behavioral Guidelines")

    Returns:
        Content of the specified section, or None if not found

    Example:
        >>> persona = agent.persona_content
        >>> behavioral_guidelines = extract_persona_section(
        ...     persona, "Behavioral Guidelines"
        ... )
        >>> # Use only behavioral guidelines in prompt
    """
    if not persona_content or not section_name:
        return None

    lines = persona_content.split("\n")
    section_lines = []
    in_section = False
    section_level = 0

    for line in lines:
        # Check if this is a heading
        stripped = line.strip()
        if stripped.startswith("#"):
            # Count the heading level
            heading_level = 0
            for char in stripped:
                if char == "#":
                    heading_level += 1
                else:
                    break
            heading_text = stripped[heading_level:].strip()

            if heading_text.lower() == section_name.lower():
                # Found the target section
                in_section = True
                section_level = heading_level
                section_lines.append(line)
            elif in_section and heading_level <= section_level:
                # Reached a same-level or higher-level heading, end section
                break
            elif in_section:
                # This is a subsection within our target section
                section_lines.append(line)
        elif in_section:
            section_lines.append(line)

    if section_lines:
        return "\n".join(section_lines).strip()
    return None
