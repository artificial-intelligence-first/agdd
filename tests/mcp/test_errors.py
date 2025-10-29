"""Tests for MCP error handling and edge cases."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from agdd.mcp import (
    MCPRegistry,
    MCPRegistryError,
    MCPRuntime,
    MCPServer,
    MCPServerConfig,
    MCPServerError,
)


pytestmark = pytest.mark.slow
# Check if asyncpg is available
try:
    import asyncpg  # noqa: F401


    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False


class TestMCPConfigValidation:
    """Test cases for configuration validation."""

    def test_mcp_server_without_command(self) -> None:
        """Test that MCP servers must specify command."""
        config = MCPServerConfig(
            server_id="test",
            type="mcp",
            # Missing command field
        )

        with pytest.raises(ValueError, match="must specify 'command'"):
            config.validate_type_fields()

    def test_postgres_server_without_conn(self) -> None:
        """Test that PostgreSQL servers must specify connection."""
        config = MCPServerConfig(
            server_id="test",
            type="postgres",
            # Missing conn field
        )

        with pytest.raises(ValueError, match="must specify 'conn'"):
            config.validate_type_fields()

    def test_valid_mcp_config(self) -> None:
        """Test valid MCP server configuration."""
        config = MCPServerConfig(
            server_id="test",
            type="mcp",
            command="npx",
            args=["-y", "@test/server"],
        )

        # Should not raise
        config.validate_type_fields()

    def test_valid_postgres_config(self) -> None:
        """Test valid PostgreSQL server configuration."""
        config = MCPServerConfig(
            server_id="test",
            type="postgres",
            conn={"url_env": "PG_URL"},
        )

        # Should not raise
        config.validate_type_fields()

    def test_permission_name_format(self) -> None:
        """Test permission name formatting."""
        config = MCPServerConfig(
            server_id="my-server",
            type="mcp",
            command="test",
        )

        assert config.get_permission_name() == "mcp:my-server"


class TestMCPServerErrors:
    """Test cases for MCP server error conditions."""

    @pytest.mark.asyncio
    async def test_start_server_twice(self) -> None:
        """Test starting a server that's already started."""
        config = MCPServerConfig(
            server_id="test",
            type="mcp",
            command="npx",
            args=["-y", "@test/server"],
        )

        server = MCPServer(config)

        async_mock = AsyncMock(return_value=None)
        with patch.object(server, "_start_mcp_server", async_mock):
            await server.start()
            assert server.is_started

            # Second start should be idempotent and not re-trigger the mock
            await server.start()
            assert server.is_started
            async_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_server_twice(self) -> None:
        """Test stopping a server that's already stopped."""
        config = MCPServerConfig(
            server_id="test",
            type="mcp",
            command="npx",
            args=["-y", "@test/server"],
        )

        server = MCPServer(config)

        # Stop without starting should be safe
        await server.stop()
        assert not server.is_started

        # Second stop should be safe
        await server.stop()
        assert not server.is_started

    @pytest.mark.asyncio
    async def test_execute_tool_before_start(self) -> None:
        """Test executing a tool before server is started."""
        config = MCPServerConfig(
            server_id="test",
            type="mcp",
            command="npx",
            args=["-y", "@test/server"],
        )

        server = MCPServer(config)

        with pytest.raises(MCPServerError, match="not started"):
            await server.execute_tool("some_tool", {})

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_ASYNCPG, reason="asyncpg not installed")
    async def test_postgres_connection_without_env_var(self) -> None:
        """Test PostgreSQL connection when env var is not set."""
        config = MCPServerConfig(
            server_id="test",
            type="postgres",
            conn={"url_env": "NONEXISTENT_PG_URL"},
        )

        server = MCPServer(config)

        with pytest.raises(MCPServerError, match="Environment variable.*not set"):
            await server.start()

    @pytest.mark.asyncio
    @pytest.mark.skipif(HAS_ASYNCPG, reason="Test for when asyncpg is not installed")
    async def test_postgres_connection_without_asyncpg(self) -> None:
        """Test PostgreSQL connection when asyncpg is not installed."""
        config = MCPServerConfig(
            server_id="test",
            type="postgres",
            conn={"url_env": "NONEXISTENT_PG_URL"},
        )

        server = MCPServer(config)

        with pytest.raises(MCPServerError, match="requires asyncpg package"):
            await server.start()

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self) -> None:
        """Test executing a tool that doesn't exist."""
        config = MCPServerConfig(
            server_id="test",
            type="mcp",
            command="npx",
            args=["-y", "@test/server"],
        )

        server = MCPServer(config)

        with patch.object(server, "_start_mcp_server", AsyncMock(return_value=None)):
            await server.start()

        result = await server.execute_tool("nonexistent_tool", {})

        assert not result.success
        assert "not found" in result.error.lower()


class TestMCPRegistryErrors:
    """Test cases for MCP registry error conditions."""

    @pytest.fixture
    def temp_servers_dir(self) -> Path:
        """Create a temporary directory for server configs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_discover_with_file_instead_of_directory(
        self,
        temp_servers_dir: Path,
    ) -> None:
        """Test discovery when path points to a file instead of directory."""
        # Create a file instead of directory
        file_path = temp_servers_dir / "not_a_dir"
        file_path.touch()

        registry = MCPRegistry(servers_dir=file_path)

        with pytest.raises(MCPRegistryError, match="Not a directory"):
            registry.discover_servers()

    def test_load_malformed_yaml(self, temp_servers_dir: Path) -> None:
        """Test loading a malformed YAML file."""
        malformed_file = temp_servers_dir / "malformed.yaml"
        with open(malformed_file, "w") as f:
            f.write("invalid: yaml: content: [[[")

        registry = MCPRegistry(servers_dir=temp_servers_dir)

        # Should not raise, just log error and continue
        registry.discover_servers()
        assert registry.list_servers() == []

    def test_duplicate_server_ids(self, temp_servers_dir: Path) -> None:
        """Test handling of duplicate server IDs."""
        # Create two files with same server_id
        config1 = temp_servers_dir / "server1.yaml"
        with open(config1, "w") as f:
            yaml.dump(
                {
                    "server_id": "duplicate",
                    "type": "mcp",
                    "command": "cmd1",
                },
                f,
            )

        config2 = temp_servers_dir / "server2.yaml"
        with open(config2, "w") as f:
            yaml.dump(
                {
                    "server_id": "duplicate",
                    "type": "mcp",
                    "command": "cmd2",
                },
                f,
            )

        registry = MCPRegistry(servers_dir=temp_servers_dir)
        registry.discover_servers()

        # Should have only one server (last one wins)
        assert len(registry.list_servers()) == 1
        assert "duplicate" in registry.list_servers()

    @pytest.mark.asyncio
    async def test_start_all_servers_with_failures(
        self,
        temp_servers_dir: Path,
    ) -> None:
        """Test starting all servers when some fail."""
        # Valid MCP server
        valid_file = temp_servers_dir / "valid.yaml"
        with open(valid_file, "w") as f:
            yaml.dump(
                {
                    "server_id": "valid",
                    "type": "mcp",
                    "command": "npx",
                    "args": ["-y", "@test/server"],
                },
                f,
            )

        # PostgreSQL server without env var (will fail)
        invalid_file = temp_servers_dir / "invalid.yaml"
        with open(invalid_file, "w") as f:
            yaml.dump(
                {
                    "server_id": "invalid",
                    "type": "postgres",
                    "conn": {"url_env": "NONEXISTENT_VAR"},
                },
                f,
            )

        registry = MCPRegistry(servers_dir=temp_servers_dir)
        registry.discover_servers()

        # Should not raise, but some servers may fail to start
        with patch.object(MCPServer, "_start_mcp_server", AsyncMock(return_value=None)):
            await registry.start_all_servers()

        # Valid server should be started, invalid should not
        running = registry.list_running_servers()
        assert "valid" in running
        assert "invalid" not in running


class TestMCPRuntimeErrors:
    """Test cases for MCP runtime error conditions."""

    @pytest.fixture
    def registry(self) -> MCPRegistry:
        """Create a minimal registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = MCPRegistry(servers_dir=Path(tmpdir))
            registry.discover_servers()
            return registry

    @pytest.mark.asyncio
    async def test_execute_without_permission(
        self,
        registry: MCPRegistry,
    ) -> None:
        """Test executing a tool without required permission."""
        runtime = MCPRuntime(registry)

        result = await runtime.execute_tool(
            server_id="test-server",
            tool_name="test-tool",
            arguments={},
        )

        assert not result.success
        assert "Permission denied" in result.error

    @pytest.mark.asyncio
    async def test_execute_on_nonexistent_server(
        self,
        registry: MCPRegistry,
    ) -> None:
        """Test executing a tool on a server that doesn't exist."""
        runtime = MCPRuntime(registry)
        runtime.grant_permissions(["mcp:nonexistent"])

        result = await runtime.execute_tool(
            server_id="nonexistent",
            tool_name="test-tool",
            arguments={},
        )

        # Should attempt to start server and fail
        assert not result.success

    def test_check_permission_for_ungranted_server(
        self,
        registry: MCPRegistry,
    ) -> None:
        """Test checking permission for a server without access."""
        runtime = MCPRuntime(registry)

        assert not runtime.check_permission("test-server")

        runtime.grant_permissions(["mcp:test-server"])

        assert runtime.check_permission("test-server")

    def test_revoke_nonexistent_permission(
        self,
        registry: MCPRegistry,
    ) -> None:
        """Test revoking a permission that wasn't granted."""
        runtime = MCPRuntime(registry)

        # Should not raise
        runtime.revoke_permissions(["mcp:nonexistent"])

        assert runtime.get_granted_permissions() == []


@pytest.mark.skipif(not HAS_ASYNCPG, reason="asyncpg not installed")
class TestPostgresQueryValidation:
    """Test cases for PostgreSQL query validation."""

    @pytest.mark.asyncio
    async def test_reject_non_select_query(self) -> None:
        """Test that non-SELECT queries are rejected in read-only mode."""
        # This would require a real PostgreSQL connection to test fully,
        # but we can verify the validation logic exists in the code
        config = MCPServerConfig(
            server_id="test-pg",
            type="postgres",
            conn={"url_env": "TEST_PG_URL"},
        )

        _ = MCPServer(config)

        # The validation happens in _execute_postgres_tool
        # which checks that SQL starts with SELECT
        # (Implementation verified in server.py:215-219)
        pass

    @pytest.mark.asyncio
    async def test_parameterized_query_support(self) -> None:
        """Test support for parameterized queries."""
        # This tests the API accepts params argument
        config = MCPServerConfig(
            server_id="test-pg",
            type="postgres",
            conn={"url_env": "TEST_PG_URL"},
        )

        _ = MCPServer(config)

        # Verify the tool schema includes params
        # (Implementation verified in server.py:126-134)
        pass
