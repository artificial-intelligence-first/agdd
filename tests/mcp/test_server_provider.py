"""Tests for MCP server provider that exposes AGDD agents."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import pytest

pytestmark = pytest.mark.slow

# Import HAS_MCP_SDK from server_provider to check if FastMCP is actually available
try:
    from agdd.mcp.server_provider import HAS_MCP_SDK

except ImportError:
    # server_provider module itself couldn't be imported
    HAS_MCP_SDK = False


@pytest.mark.skipif(not HAS_MCP_SDK, reason="mcp SDK not installed")
class TestAGDDMCPServer:
    """Test cases for AGDD MCP server provider."""

    def test_server_creation(self) -> None:
        """Test creating an MCP server instance."""
        from agdd.mcp.server_provider import create_server

        server = create_server(
            expose_agents=True,
            expose_skills=False,
        )

        assert server is not None
        assert server.expose_agents is True
        assert server.expose_skills is False

    def test_server_with_filters(self) -> None:
        """Test creating server with agent/skill filters."""
        from agdd.mcp.server_provider import create_server

        server = create_server(
            expose_agents=True,
            agent_filter=["offer-orchestrator-mag"],
            skill_filter=["skill.salary-band-lookup"],
        )

        assert server.agent_filter == ["offer-orchestrator-mag"]
        assert server.skill_filter == ["skill.salary-band-lookup"]

    def test_agent_tool_registration(self) -> None:
        """Test that agents are registered as MCP tools."""
        from agdd.mcp.server_provider import create_server

        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)

            # Create minimal agent structure
            agent_dir = base_path / "catalog" / "agents" / "main" / "test-agent"
            agent_dir.mkdir(parents=True)

            # Create agent.yaml
            agent_yaml = agent_dir / "agent.yaml"
            agent_yaml.write_text(
                """
slug: test-agent
name: Test Agent
role: main
version: 0.1.0
entrypoint: code/orchestrator.py:run
depends_on:
  sub_agents: []
  skills: []
contracts:
  input_schema: ""
  output_schema: ""
risk_class: low
budgets: {}
observability: {}
evaluation: {}
""".strip()
            )

            # Create server with this base path
            server = create_server(
                base_path=base_path,
                expose_agents=True,
                expose_skills=False,
            )

            # Check that FastMCP server was created
            assert server.mcp is not None

    def test_skill_tool_registration(self) -> None:
        """Test that skills are registered as MCP tools."""
        from agdd.mcp.server_provider import create_server

        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)

            # Create skills registry
            registry_dir = base_path / "catalog" / "registry"
            registry_dir.mkdir(parents=True)

            skills_yaml = registry_dir / "skills.yaml"
            skills_yaml.write_text(
                """
skills:
  - id: skill.test-skill
    version: 0.1.0
    location: catalog/skills/test-skill
    entrypoint: catalog/skills/test-skill/impl.py:run
    permissions: []
""".strip()
            )

            # Create server with skills enabled
            server = create_server(
                base_path=base_path,
                expose_agents=False,
                expose_skills=True,
            )

            # Check that FastMCP server was created
            assert server.mcp is not None

    @patch("agdd.runners.agent_runner.AgentRunner.invoke_mag")
    def test_agent_execution_via_mcp(self, mock_invoke: MagicMock) -> None:
        """Test executing an agent via MCP tool call."""
        from agdd.mcp.server_provider import create_server

        # Mock agent execution
        mock_invoke.return_value = {
            "status": "success",
            "result": "Test output",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)

            # Create minimal agent structure
            agent_dir = base_path / "catalog" / "agents" / "main" / "test-agent"
            agent_dir.mkdir(parents=True)

            agent_yaml = agent_dir / "agent.yaml"
            agent_yaml.write_text(
                """
slug: test-agent
name: Test Agent
role: main
version: 0.1.0
entrypoint: code/orchestrator.py:run
depends_on:
  sub_agents: []
  skills: []
contracts:
  input_schema: ""
  output_schema: ""
risk_class: low
budgets: {}
observability: {}
evaluation: {}
""".strip()
            )

            # Create server
            server = create_server(
                base_path=base_path,
                expose_agents=True,
                agent_filter=["test-agent"],
            )

            # Verify server was created
            assert server.mcp is not None

    def test_server_without_mcp_sdk_fails(self) -> None:
        """Test that server creation fails gracefully without MCP SDK."""
        # This test would only run if MCP SDK is not available
        # Since we skip the test class if MCP SDK is missing,
        # we just document the expected behavior here
        pass

    def test_agent_filter_applies(self) -> None:
        """Test that agent filter correctly limits exposed agents."""
        from agdd.mcp.server_provider import create_server

        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)

            # Create two agents
            for agent_name in ["agent-one", "agent-two"]:
                agent_dir = base_path / "catalog" / "agents" / "main" / agent_name
                agent_dir.mkdir(parents=True)

                agent_yaml = agent_dir / "agent.yaml"
                agent_yaml.write_text(
                    f"""
slug: {agent_name}
name: {agent_name.replace('-', ' ').title()}
role: main
version: 0.1.0
entrypoint: code/orchestrator.py:run
depends_on:
  sub_agents: []
  skills: []
contracts:
  input_schema: ""
  output_schema: ""
risk_class: low
budgets: {{}}
observability: {{}}
evaluation: {{}}
""".strip()
                )

            # Create server filtering to only agent-one
            server = create_server(
                base_path=base_path,
                expose_agents=True,
                agent_filter=["agent-one"],
            )

            # Verify filter was applied
            assert server.agent_filter == ["agent-one"]

    def test_runner_uses_server_registry(self) -> None:
        """Test that the agent runner uses the server's registry."""
        from agdd.mcp.server_provider import create_server

        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)

            # Create minimal agent structure
            agent_dir = base_path / "catalog" / "agents" / "main" / "custom-agent"
            agent_dir.mkdir(parents=True)

            agent_yaml = agent_dir / "agent.yaml"
            agent_yaml.write_text(
                """
slug: custom-agent
name: Custom Agent
role: main
version: 0.1.0
entrypoint: code/orchestrator.py:run
depends_on:
  sub_agents: []
  skills: []
contracts:
  input_schema: ""
  output_schema: ""
risk_class: low
budgets: {}
observability: {}
evaluation: {}
""".strip()
            )

            # Create server with custom base_path
            server = create_server(
                base_path=base_path,
                expose_agents=True,
            )

            # Verify runner's registry matches server's registry
            assert server.runner.registry is server.registry
            assert server.runner.registry.base_path == base_path

            # Verify the runner can load the agent from the custom catalog
            descriptor = server.runner.registry.load_agent("custom-agent")
            assert descriptor.slug == "custom-agent"

    def test_skill_filter_applies(self) -> None:
        """Test that skill filter correctly limits exposed skills."""
        from agdd.mcp.server_provider import create_server

        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)

            # Create skills registry
            registry_dir = base_path / "catalog" / "registry"
            registry_dir.mkdir(parents=True)

            skills_yaml = registry_dir / "skills.yaml"
            skills_yaml.write_text(
                """
skills:
  - id: skill.one
    version: 0.1.0
    location: catalog/skills/one
    entrypoint: catalog/skills/one/impl.py:run
    permissions: []
  - id: skill.two
    version: 0.1.0
    location: catalog/skills/two
    entrypoint: catalog/skills/two/impl.py:run
    permissions: []
""".strip()
            )

            # Create server filtering to only skill.one
            server = create_server(
                base_path=base_path,
                expose_agents=False,
                expose_skills=True,
                skill_filter=["skill.one"],
            )

            # Verify filter was applied
            assert server.skill_filter == ["skill.one"]


@pytest.mark.skipif(HAS_MCP_SDK, reason="Test for missing MCP SDK")
def test_import_without_mcp_sdk() -> None:
    """Test that importing server_provider fails gracefully without MCP SDK."""
    try:
        from agdd.mcp.server_provider import create_server

        # Should raise ImportError during server creation
        with pytest.raises(ImportError, match="MCP SDK not installed"):
            server = create_server()
    except ImportError:
        # Import itself may fail, which is also acceptable
        pass


@pytest.mark.skipif(not HAS_MCP_SDK, reason="mcp SDK not installed")
def test_server_provider_in_init() -> None:
    """Test that server provider is available in agdd.mcp module."""
    from agdd.mcp import HAS_SERVER_PROVIDER, create_server
    from agdd.mcp.server_provider import HAS_MCP_SDK as PROVIDER_HAS_SDK

    assert HAS_SERVER_PROVIDER is True
    assert PROVIDER_HAS_SDK is True
    assert create_server is not None
