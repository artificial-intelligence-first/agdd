"""Test async-only requirement for skills and agents."""

from typing import Any
from unittest.mock import Mock

import pytest

from agdd.runners.agent_runner import AgentRunner, SkillRuntime


class TestAsyncRequirement:
    """Test that synchronous skills and agents are properly rejected."""

    @pytest.fixture
    def mock_registry(self) -> Mock:
        """Create a mock registry."""
        registry = Mock()
        return registry

    @pytest.fixture
    def mock_observer(self) -> Mock:
        """Create a mock observer."""
        observer = Mock()
        observer.log = Mock()
        observer.metric = Mock()
        observer.cost_usd = 0
        observer.llm_plan_snapshot = {}
        return observer

    @pytest.fixture
    def skill_runtime(self, mock_registry: Mock) -> SkillRuntime:
        """Create skill runtime."""
        return SkillRuntime(registry=mock_registry, enable_mcp=False)

    @pytest.fixture
    def agent_runner(self, mock_registry: Mock) -> AgentRunner:
        """Create agent runner."""
        runner = AgentRunner(registry=mock_registry)
        runner.enable_mcp = False
        return runner

    @pytest.mark.asyncio
    async def test_sync_skill_raises_error(
        self, skill_runtime: SkillRuntime, mock_registry: Mock
    ) -> None:
        """Test that synchronous skills raise ValueError."""

        # Create a synchronous skill
        def sync_skill(payload: dict[str, Any]) -> dict[str, str]:
            return {"result": "sync"}

        # Mock registry to return our sync skill
        skill_desc = Mock()
        skill_desc.id = "test-sync-skill"
        mock_registry.load_skill.return_value = skill_desc
        mock_registry.resolve_entrypoint.return_value = sync_skill

        # Attempting to invoke a sync skill should raise ValueError
        with pytest.raises(ValueError, match="must be async"):
            await skill_runtime.invoke_async("test-sync-skill", {"test": "data"})

    @pytest.mark.asyncio
    async def test_async_skill_works(
        self, skill_runtime: SkillRuntime, mock_registry: Mock
    ) -> None:
        """Test that async skills work correctly."""

        # Create an async skill
        async def async_skill(payload: dict[str, Any]) -> dict[str, str]:
            return {"result": "async"}

        # Mock registry to return our async skill
        skill_desc = Mock()
        skill_desc.id = "test-async-skill"
        mock_registry.load_skill.return_value = skill_desc
        mock_registry.resolve_entrypoint.return_value = async_skill

        # Async skill should work without issues
        result = await skill_runtime.invoke_async("test-async-skill", {"test": "data"})
        assert result == {"result": "async"}

    def test_sync_agent_raises_error(
        self, agent_runner: AgentRunner, mock_registry: Mock, mock_observer: Mock
    ) -> None:
        """Test that synchronous agents raise ValueError."""

        # Create a synchronous agent
        def sync_agent(payload: dict[str, Any], **kwargs: Any) -> dict[str, str]:
            return {"result": "sync"}

        # Mock registry to return our sync agent
        agent_desc = Mock()
        agent_desc.id = "test-sync-agent"
        agent_desc.slug = "test-sync-agent"
        agent_desc.entrypoint = "test.sync_agent"
        agent_desc.config = {}
        mock_registry.load_agent.return_value = agent_desc
        mock_registry.resolve_entrypoint.return_value = sync_agent

        # Attempting to run a sync agent should raise ValueError
        with pytest.raises(ValueError, match="must be async"):
            agent_runner.run_agent("test-sync-agent", {"test": "data"}, observer=mock_observer)

    def test_async_agent_works(
        self, agent_runner: AgentRunner, mock_registry: Mock, mock_observer: Mock
    ) -> None:
        """Test that async agents work correctly."""

        # Create an async agent
        async def async_agent(payload: dict[str, Any], **kwargs: Any) -> dict[str, str]:
            return {"result": "async"}

        # Mock registry to return our async agent
        agent_desc = Mock()
        agent_desc.id = "test-async-agent"
        agent_desc.slug = "test-async-agent"
        agent_desc.entrypoint = "test.async_agent"
        agent_desc.config = {}
        mock_registry.load_agent.return_value = agent_desc
        mock_registry.resolve_entrypoint.return_value = async_agent

        # Async agent should work without issues
        result = agent_runner.run_agent(
            "test-async-agent", {"test": "data"}, observer=mock_observer
        )
        assert result["result"] == "async"

    @pytest.mark.asyncio
    async def test_sync_skill_with_mcp_param_raises_error(
        self, skill_runtime: SkillRuntime, mock_registry: Mock
    ) -> None:
        """Test that sync skills with MCP parameter raise appropriate error."""

        # Create a synchronous skill that expects MCP
        def sync_skill_with_mcp(payload: dict[str, Any], mcp: Any | None = None) -> dict[str, str]:
            return {"result": "sync with mcp"}

        # Mock registry to return our sync skill
        skill_desc = Mock()
        skill_desc.id = "test-sync-mcp-skill"
        mock_registry.load_skill.return_value = skill_desc
        mock_registry.resolve_entrypoint.return_value = sync_skill_with_mcp

        # Should raise ValueError about sync skills not being supported
        with pytest.raises(ValueError, match="must be async"):
            await skill_runtime.invoke_async("test-sync-mcp-skill", {"test": "data"})

    def test_error_message_is_helpful(
        self, skill_runtime: SkillRuntime, mock_registry: Mock
    ) -> None:
        """Test that error messages for sync skills are helpful."""

        # Create a synchronous skill
        def problematic_sync_skill(payload: dict[str, Any]) -> dict[str, str]:
            return {"result": "sync"}

        # Mock registry to return our sync skill
        skill_desc = Mock()
        skill_desc.id = "my-important-skill"
        mock_registry.load_skill.return_value = skill_desc
        mock_registry.resolve_entrypoint.return_value = problematic_sync_skill

        # Check that the error message includes the skill name
        with pytest.raises(ValueError) as exc_info:
            import asyncio

            asyncio.run(skill_runtime.invoke_async("my-important-skill", {"test": "data"}))

        error_message = str(exc_info.value)
        assert "my-important-skill" in error_message
        assert "must be async" in error_message
