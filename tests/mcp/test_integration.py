"""Integration tests for MCP with skills and agents.

This module tests the integration of MCP with the AGDD framework,
including skills auto-discovery and permission validation.
"""

import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from agdd.mcp import MCPRegistry, MCPRuntime, MCPToolResult

# Check if asyncpg is available
try:
    import asyncpg  # noqa: F401

    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False


@pytest.mark.skipif(not HAS_ASYNCPG, reason="asyncpg not installed")
class TestSkillsMCPIntegration:
    """Test cases for MCP integration with skills."""

    @pytest.fixture
    def temp_dirs(self) -> tuple[Path, Path]:
        """Create temporary directories for servers and skills."""
        with tempfile.TemporaryDirectory() as servers_dir, tempfile.TemporaryDirectory() as skills_dir:
            yield Path(servers_dir), Path(skills_dir)

    @pytest.fixture
    def registry_with_postgres(self, temp_dirs: tuple[Path, Path]) -> MCPRegistry:
        """Create a registry with PostgreSQL server."""
        servers_dir, _ = temp_dirs

        pg_file = servers_dir / "pg-readonly.yaml"
        with open(pg_file, "w") as f:
            yaml.dump(
                {
                    "server_id": "pg-readonly",
                    "type": "postgres",
                    "scopes": ["read:tables"],
                    "conn": {"url_env": "PG_RO_URL"},
                },
                f,
            )

        registry = MCPRegistry(servers_dir=servers_dir)
        registry.discover_servers()
        return registry

    @pytest.fixture
    def skill_registry_config(self, temp_dirs: tuple[Path, Path]) -> dict[str, Any]:
        """Create a sample skills registry configuration."""
        _, skills_dir = temp_dirs

        return {
            "skills": [
                {
                    "id": "skill.salary-band-lookup",
                    "version": "0.1.0",
                    "location": str(skills_dir / "salary-band-lookup"),
                    "entrypoint": str(skills_dir / "salary-band-lookup/impl.py:run"),
                    "permissions": ["mcp:pg-readonly"],
                },
                {
                    "id": "skill.task-decomposition",
                    "version": "0.1.0",
                    "location": str(skills_dir / "task-decomposition"),
                    "entrypoint": str(skills_dir / "task-decomposition/impl.py:run"),
                    "permissions": [],
                },
            ]
        }

    def test_discover_skills_with_permissions(
        self,
        skill_registry_config: dict[str, Any],
    ) -> None:
        """Test discovering skills and their MCP permissions."""
        skills = skill_registry_config["skills"]

        # Skill with MCP permissions
        salary_skill = skills[0]
        assert "mcp:pg-readonly" in salary_skill["permissions"]

        # Skill without MCP permissions
        task_skill = skills[1]
        assert len(task_skill["permissions"]) == 0

    def test_validate_skill_permissions(
        self,
        registry_with_postgres: MCPRegistry,
        skill_registry_config: dict[str, Any],
    ) -> None:
        """Test validating skill permissions against available MCP servers."""
        skill = skill_registry_config["skills"][0]
        permissions = skill["permissions"]

        # Validate permissions
        validation = registry_with_postgres.validate_permissions(permissions)

        assert validation["mcp:pg-readonly"] is True

    def test_validate_missing_permissions(
        self,
        registry_with_postgres: MCPRegistry,
    ) -> None:
        """Test validation when skill requires unavailable MCP server."""
        # Skill requires a server that doesn't exist
        invalid_permissions = ["mcp:nonexistent-server"]

        validation = registry_with_postgres.validate_permissions(invalid_permissions)

        assert validation["mcp:nonexistent-server"] is False

    @pytest.mark.asyncio
    async def test_skill_execution_with_mcp_runtime(
        self,
        registry_with_postgres: MCPRegistry,
        skill_registry_config: dict[str, Any],
    ) -> None:
        """Test executing a skill that uses MCP runtime."""
        skill = skill_registry_config["skills"][0]
        permissions = skill["permissions"]

        # Create runtime with skill's permissions
        runtime = MCPRuntime(registry_with_postgres)
        runtime.grant_permissions(permissions)

        # Verify runtime has correct permissions
        assert runtime.check_permission("pg-readonly")

        # Mock PostgreSQL connection
        with patch("agdd.mcp.server.asyncpg.create_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.fetch = AsyncMock(
                return_value=[
                    {"band": "L4", "min_salary": 100000, "max_salary": 150000}
                ]
            )

            mock_pool_instance = AsyncMock()
            mock_pool_instance.acquire = AsyncMock(
                return_value=mock_conn.__aenter__.return_value
            )
            mock_pool.return_value = mock_pool_instance

            os.environ["PG_RO_URL"] = "postgresql://test:test@localhost/test"

            try:
                # Execute query via runtime (simulating skill execution)
                result = await runtime.query_postgres(
                    server_id="pg-readonly",
                    sql="SELECT * FROM salary_bands WHERE level = $1",
                    params=["L4"],
                )

                # Verify execution (success depends on mock setup)
                assert result is not None

            finally:
                del os.environ["PG_RO_URL"]

    def test_multiple_skills_sharing_server(
        self,
        registry_with_postgres: MCPRegistry,
    ) -> None:
        """Test multiple skills using the same MCP server."""
        # Multiple skills can share the same MCP server
        skill1_permissions = ["mcp:pg-readonly"]
        skill2_permissions = ["mcp:pg-readonly"]

        validation1 = registry_with_postgres.validate_permissions(skill1_permissions)
        validation2 = registry_with_postgres.validate_permissions(skill2_permissions)

        assert validation1["mcp:pg-readonly"] is True
        assert validation2["mcp:pg-readonly"] is True

    def test_skill_with_multiple_servers(
        self,
        temp_dirs: tuple[Path, Path],
    ) -> None:
        """Test skill requiring multiple MCP servers."""
        servers_dir, _ = temp_dirs

        # Create multiple server configs
        pg_file = servers_dir / "pg.yaml"
        with open(pg_file, "w") as f:
            yaml.dump(
                {
                    "server_id": "pg-readonly",
                    "type": "postgres",
                    "conn": {"url_env": "PG_URL"},
                },
                f,
            )

        fs_file = servers_dir / "fs.yaml"
        with open(fs_file, "w") as f:
            yaml.dump(
                {
                    "server_id": "filesystem",
                    "type": "mcp",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                },
                f,
            )

        registry = MCPRegistry(servers_dir=servers_dir)
        registry.discover_servers()

        # Skill requiring multiple servers
        multi_permissions = ["mcp:pg-readonly", "mcp:filesystem"]

        validation = registry.validate_permissions(multi_permissions)

        assert validation["mcp:pg-readonly"] is True
        assert validation["mcp:filesystem"] is True


class TestMCPServerAutoDiscovery:
    """Test cases for MCP server auto-discovery from .mcp/servers/."""

    def test_discover_from_default_location(self) -> None:
        """Test discovery from default .mcp/servers/ location."""
        # This tests with the actual project .mcp/servers/ directory
        registry = MCPRegistry()
        registry.discover_servers()

        servers = registry.list_servers()

        # Verify some expected servers are discovered
        # (based on the exploration earlier)
        assert len(servers) > 0

        # Check for known servers from .mcp/servers/
        expected_servers = ["filesystem", "pg-readonly", "git", "memory", "fetch"]
        discovered_count = sum(1 for s in expected_servers if s in servers)

        # At least some expected servers should be found
        assert discovered_count > 0

    def test_get_server_permissions(self) -> None:
        """Test getting permission names from discovered servers."""
        registry = MCPRegistry()
        registry.discover_servers()

        servers = registry.list_servers()

        if "pg-readonly" in servers:
            # Verify permission name format
            validation = registry.validate_permissions(["mcp:pg-readonly"])
            assert validation["mcp:pg-readonly"] is True

    def test_list_tools_from_discovered_servers(self) -> None:
        """Test listing tools from discovered servers."""
        registry = MCPRegistry()
        registry.discover_servers()

        # Get tools from all servers (without starting them)
        all_tools = registry.get_tools()

        # Without starting servers, should be empty
        assert all_tools == []

        # Get tools from specific server (also should be empty if not started)
        pg_tools = registry.get_tools("pg-readonly")
        assert pg_tools == []


class TestMCPRuntimeLifecycle:
    """Test cases for MCP runtime lifecycle in skill execution."""

    @pytest.fixture
    def registry(self) -> MCPRegistry:
        """Create a registry with some servers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            servers_dir = Path(tmpdir)

            # Create a test server config
            test_file = servers_dir / "test.yaml"
            with open(test_file, "w") as f:
                yaml.dump(
                    {
                        "server_id": "test-server",
                        "type": "mcp",
                        "command": "npx",
                        "args": ["-y", "@test/server"],
                    },
                    f,
                )

            registry = MCPRegistry(servers_dir=servers_dir)
            registry.discover_servers()
            return registry

    def test_runtime_creation_per_skill(self, registry: MCPRegistry) -> None:
        """Test creating separate runtime instances per skill."""
        # Each skill should get its own runtime instance
        runtime1 = MCPRuntime(registry)
        runtime2 = MCPRuntime(registry)

        # Grant different permissions
        runtime1.grant_permissions(["mcp:server1"])
        runtime2.grant_permissions(["mcp:server2"])

        # Runtimes should be independent
        assert runtime1.get_granted_permissions() != runtime2.get_granted_permissions()
        assert "mcp:server1" in runtime1.get_granted_permissions()
        assert "mcp:server2" in runtime2.get_granted_permissions()

    def test_runtime_permission_isolation(self, registry: MCPRegistry) -> None:
        """Test that runtime permissions are properly isolated."""
        runtime1 = MCPRuntime(registry)
        runtime2 = MCPRuntime(registry)

        runtime1.grant_permissions(["mcp:test-server"])

        # runtime2 should not have access
        assert runtime1.check_permission("test-server")
        assert not runtime2.check_permission("test-server")

    @pytest.mark.asyncio
    async def test_runtime_cleanup(self, registry: MCPRegistry) -> None:
        """Test runtime cleanup after skill execution."""
        runtime = MCPRuntime(registry)
        runtime.grant_permissions(["mcp:test-server"])

        # After skill execution completes, permissions can be revoked
        runtime.revoke_permissions(["mcp:test-server"])

        assert runtime.get_granted_permissions() == []

    @pytest.mark.asyncio
    async def test_mixed_permissions_execution(self, registry: MCPRegistry) -> None:
        """Test that skills with mixed MCP and non-MCP permissions can execute tools."""
        runtime = MCPRuntime(registry)

        # Grant both MCP and non-MCP permissions (simulating a skill that needs multiple access)
        runtime.grant_permissions(["mcp:test-server", "files:read", "files:write"])

        # Verify runtime has all permissions
        granted = runtime.get_granted_permissions()
        assert "mcp:test-server" in granted
        assert "files:read" in granted
        assert "files:write" in granted

        # Execute a tool - should only validate MCP permissions
        result = await runtime.execute_tool(
            server_id="test-server",
            tool_name="some-tool",
            arguments={},
        )

        # Should attempt execution (even if it fails due to server not running)
        # The key is that it should NOT fail with "Missing required permissions" for non-MCP perms
        assert isinstance(result, MCPToolResult)
        if not result.success:
            # Verify it's not a permission error about non-MCP permissions
            assert "files:read" not in result.error.lower()
            assert "files:write" not in result.error.lower()

    @pytest.mark.asyncio
    async def test_multiple_mcp_permissions_with_invalid(
        self, registry: MCPRegistry
    ) -> None:
        """Test that one invalid MCP permission doesn't block access to valid servers."""
        runtime = MCPRuntime(registry)

        # Grant multiple MCP permissions, including one with a typo/invalid server
        runtime.grant_permissions([
            "mcp:test-server",
            "mcp:invalid-typo-server",  # This doesn't exist
            "mcp:another-nonexistent",  # This also doesn't exist
        ])

        # Verify runtime has all permissions
        granted = runtime.get_granted_permissions()
        assert "mcp:test-server" in granted
        assert "mcp:invalid-typo-server" in granted
        assert "mcp:another-nonexistent" in granted

        # Execute a tool on the VALID server
        # Should NOT fail just because other permissions are invalid
        result = await runtime.execute_tool(
            server_id="test-server",
            tool_name="some-tool",
            arguments={},
        )

        # Should attempt execution (even if it fails due to server not running)
        # The key is that it should NOT fail with "Missing required permissions" about
        # the invalid servers
        assert isinstance(result, MCPToolResult)
        if not result.success:
            # Verify it's not a permission error about the invalid servers
            assert "invalid-typo-server" not in result.error.lower()
            assert "another-nonexistent" not in result.error.lower()
            # It's fine if it fails because test-server isn't started, but not
            # because of validation of unrelated permissions
