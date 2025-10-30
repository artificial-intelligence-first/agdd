"""Unit tests for persona utilities"""

from agdd.persona import (
    build_system_prompt_with_persona,
    get_agent_persona,
    extract_persona_section,
)
from agdd.registry import Registry


class TestBuildSystemPromptWithPersona:
    """Test build_system_prompt_with_persona function"""

    def test_with_persona(self) -> None:
        """Test combining base prompt with persona"""
        base = "You are a helpful assistant."
        persona = "Be professional and concise."

        result = build_system_prompt_with_persona(base, persona)

        assert "Be professional and concise." in result
        assert "You are a helpful assistant." in result
        assert result.index("Be professional") < result.index("helpful assistant")

    def test_without_persona(self) -> None:
        """Test with no persona content"""
        base = "You are a helpful assistant."

        result = build_system_prompt_with_persona(base, None)

        assert result == base

    def test_empty_persona(self) -> None:
        """Test with empty persona string"""
        base = "You are a helpful assistant."

        result = build_system_prompt_with_persona(base, "")

        assert result == base

    def test_custom_separator(self) -> None:
        """Test with custom separator"""
        base = "Task instructions"
        persona = "Persona content"
        separator = "\n\n***\n\n"

        result = build_system_prompt_with_persona(base, persona, separator=separator)

        assert "***" in result
        assert result.index("Persona") < result.index("***") < result.index("Task")


class TestGetAgentPersona:
    """Test get_agent_persona function"""

    def test_get_persona_mag(self) -> None:
        """Test retrieving persona for MAG agent"""
        registry = Registry()
        persona = get_agent_persona("offer-orchestrator-mag", registry=registry)

        assert persona is not None
        assert isinstance(persona, str)
        assert len(persona) > 0
        assert "Personality" in persona

    def test_get_persona_sag(self) -> None:
        """Test retrieving persona for SAG agent"""
        registry = Registry()
        persona = get_agent_persona("compensation-advisor-sag", registry=registry)

        assert persona is not None
        assert isinstance(persona, str)
        assert len(persona) > 0
        assert "Personality" in persona

    def test_get_persona_with_global_registry(self) -> None:
        """Test retrieving persona using global registry"""
        # Should work without explicit registry parameter
        persona = get_agent_persona("offer-orchestrator-mag")

        assert persona is not None
        assert isinstance(persona, str)


class TestExtractPersonaSection:
    """Test extract_persona_section function"""

    def test_extract_existing_section(self) -> None:
        """Test extracting an existing section"""
        persona_content = """# Agent Persona

## Personality
Professional and concise

## Tone & Style
- Formal
- Technical

## Behavioral Guidelines
- Be helpful
- Ask questions
"""

        result = extract_persona_section(persona_content, "Behavioral Guidelines")

        assert result is not None
        assert "## Behavioral Guidelines" in result
        assert "Be helpful" in result
        assert "Ask questions" in result
        # Should not include the next section
        assert "Tone & Style" not in result

    def test_extract_nonexistent_section(self) -> None:
        """Test extracting a section that doesn't exist"""
        persona_content = """# Agent Persona

## Personality
Professional and concise
"""

        result = extract_persona_section(persona_content, "Nonexistent Section")

        assert result is None

    def test_extract_section_case_insensitive(self) -> None:
        """Test section extraction is case-insensitive"""
        persona_content = """# Agent Persona

## Behavioral Guidelines
Content here
"""

        result = extract_persona_section(persona_content, "behavioral guidelines")

        assert result is not None
        assert "Behavioral Guidelines" in result

    def test_extract_from_empty_content(self) -> None:
        """Test extracting from empty content"""
        result = extract_persona_section("", "Any Section")

        assert result is None

    def test_extract_with_empty_section_name(self) -> None:
        """Test extracting with empty section name"""
        persona_content = """# Agent Persona

## Personality
Professional
"""

        result = extract_persona_section(persona_content, "")

        assert result is None

    def test_extract_nested_sections(self) -> None:
        """Test extracting section with nested sub-sections"""
        persona_content = """# Agent Persona

## Behavioral Guidelines

### When Uncertain
- Ask for clarification

### Providing Information
- Be clear and concise

## Response Patterns
Different section
"""

        result = extract_persona_section(persona_content, "Behavioral Guidelines")

        assert result is not None
        assert "## Behavioral Guidelines" in result
        assert "When Uncertain" in result
        assert "Providing Information" in result
        # Should stop before next top-level section
        assert "Response Patterns" not in result


class TestPersonaIntegration:
    """Integration tests for persona utilities"""

    def test_full_workflow(self) -> None:
        """Test complete workflow: load agent, build prompt"""
        registry = Registry()

        # Get agent persona
        persona = get_agent_persona("offer-orchestrator-mag", registry=registry)
        assert persona is not None

        # Build system prompt
        base_prompt = "Generate a compensation offer for the candidate."
        system_prompt = build_system_prompt_with_persona(base_prompt, persona)

        # Verify persona is included
        assert len(system_prompt) > len(base_prompt)
        assert "Personality" in system_prompt
        assert "Generate a compensation offer" in system_prompt

    def test_extract_and_use_section(self) -> None:
        """Test extracting specific section and using it"""
        registry = Registry()
        agent = registry.load_agent("offer-orchestrator-mag")

        # Extract specific section
        guidelines = extract_persona_section(agent.persona_content or "", "Behavioral Guidelines")

        assert guidelines is not None
        assert "Behavioral Guidelines" in guidelines

        # Use in prompt
        prompt = build_system_prompt_with_persona("Complete this task.", guidelines)

        assert "Behavioral Guidelines" in prompt
        assert "Complete this task" in prompt
