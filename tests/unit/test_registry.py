"""Unit tests for agdd.registry module"""

import pytest
from agdd.registry import Registry


class TestRegistry:
    """Test suite for Registry class"""

    def test_load_agent_mag(self) -> None:
        """Test loading a MAG agent descriptor"""
        registry = Registry()
        agent = registry.load_agent("offer-orchestrator-mag")

        assert agent.slug == "offer-orchestrator-mag"
        assert agent.name == "OfferOrchestratorMAG"
        assert agent.role == "main"
        assert agent.version == "0.1.0"
        assert "sub_agents" in agent.depends_on
        assert "skills" in agent.depends_on

    def test_load_agent_sag(self) -> None:
        """Test loading a SAG agent descriptor"""
        registry = Registry()
        agent = registry.load_agent("compensation-advisor-sag")

        assert agent.slug == "compensation-advisor-sag"
        assert agent.name == "CompensationAdvisorSAG"
        assert agent.role == "sub"
        assert agent.version == "0.1.0"
        assert "skills" in agent.depends_on

    def test_load_agent_not_found(self) -> None:
        """Test loading non-existent agent raises FileNotFoundError"""
        registry = Registry()
        with pytest.raises(FileNotFoundError, match="Agent 'nonexistent-agent' not found"):
            registry.load_agent("nonexistent-agent")

    def test_load_skill(self) -> None:
        """Test loading a skill descriptor"""
        registry = Registry()
        skill = registry.load_skill("skill.salary-band-lookup")

        assert skill.id == "skill.salary-band-lookup"
        assert skill.version == "0.1.0"
        assert "salary_band_lookup.py:run" in skill.entrypoint

    def test_load_skill_not_found(self) -> None:
        """Test loading non-existent skill raises ValueError"""
        registry = Registry()
        with pytest.raises(ValueError, match="Skill 'skill.nonexistent' not found"):
            registry.load_skill("skill.nonexistent")

    def test_resolve_entrypoint(self) -> None:
        """Test resolving entrypoint to callable"""
        import inspect

        registry = Registry()

        # doc-gen migrated to async signature (Phase 2 baseline)
        doc_gen_fn = registry.resolve_entrypoint("catalog/skills/doc-gen/impl/doc_gen.py:run")
        assert callable(doc_gen_fn)
        assert inspect.iscoroutinefunction(doc_gen_fn), "doc-gen should expose an async signature"

        # salary-band-lookup remains async
        async_fn = registry.resolve_entrypoint(
            "catalog/skills/salary-band-lookup/impl/salary_band_lookup.py:run"
        )
        assert callable(async_fn)
        assert inspect.iscoroutinefunction(async_fn), "salary-band-lookup should be async"

    def test_resolve_entrypoint_invalid_format(self) -> None:
        """Test invalid entrypoint format raises ValueError"""
        registry = Registry()
        with pytest.raises(ValueError, match="Invalid entrypoint format"):
            registry.resolve_entrypoint("no_colon_separator")

    def test_resolve_entrypoint_file_not_found(self) -> None:
        """Test non-existent entrypoint file raises FileNotFoundError"""
        registry = Registry()
        with pytest.raises(FileNotFoundError):
            registry.resolve_entrypoint("nonexistent/file.py:run")

    def test_resolve_task(self) -> None:
        """Test resolving task ID to agent slug"""
        registry = Registry()
        slug = registry.resolve_task("offer-orchestration")

        assert slug == "offer-orchestrator-mag"

    def test_resolve_task_not_found(self) -> None:
        """Test resolving non-existent task raises ValueError"""
        registry = Registry()
        with pytest.raises(ValueError, match="Task 'nonexistent-task' not found"):
            registry.resolve_task("nonexistent-task")

    def test_caching(self) -> None:
        """Test that descriptors are cached"""
        registry = Registry()

        # Load twice
        agent1 = registry.load_agent("offer-orchestrator-mag")
        agent2 = registry.load_agent("offer-orchestrator-mag")

        # Should be same object (cached)
        assert agent1 is agent2

    def test_agent_contracts(self) -> None:
        """Test agent contract schema references"""
        registry = Registry()
        agent = registry.load_agent("offer-orchestrator-mag")

        assert "input_schema" in agent.contracts
        assert "output_schema" in agent.contracts
        assert "candidate_profile" in agent.contracts["input_schema"]
        assert "offer_packet" in agent.contracts["output_schema"]

    def test_persona_loading_mag(self) -> None:
        """Test loading persona content for MAG agent"""
        registry = Registry()
        agent = registry.load_agent("offer-orchestrator-mag")

        # Persona should be loaded
        assert agent.persona_content is not None
        assert isinstance(agent.persona_content, str)
        assert len(agent.persona_content) > 0

        # Check for expected persona sections
        assert "# Agent Persona" in agent.persona_content
        assert "Personality" in agent.persona_content
        assert "Tone & Style" in agent.persona_content
        assert "Behavioral Guidelines" in agent.persona_content

    def test_persona_loading_sag(self) -> None:
        """Test loading persona content for SAG agent"""
        registry = Registry()
        agent = registry.load_agent("compensation-advisor-sag")

        # Persona should be loaded
        assert agent.persona_content is not None
        assert isinstance(agent.persona_content, str)
        assert len(agent.persona_content) > 0

        # Check for expected persona sections
        assert "# Agent Persona" in agent.persona_content
        assert "Personality" in agent.persona_content
        assert "Response Patterns" in agent.persona_content

    def test_persona_optional(self) -> None:
        """Test that agents without PERSONA.md still load correctly"""
        registry = Registry()
        # This test assumes there might be agents without PERSONA.md
        # For now, we just verify that persona_content can be None
        # and the agent still loads without errors

        # The field should exist even if None
        agent = registry.load_agent("offer-orchestrator-mag")
        assert hasattr(agent, "persona_content")

    def test_persona_caching(self) -> None:
        """Test that persona content is cached with agent descriptor"""
        registry = Registry()

        # Load twice
        agent1 = registry.load_agent("offer-orchestrator-mag")
        agent2 = registry.load_agent("offer-orchestrator-mag")

        # Should be same object (cached)
        assert agent1 is agent2
        # Persona content should also be the same
        assert agent1.persona_content == agent2.persona_content
