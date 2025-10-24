"""Tests for MCP Registry auto-discovery functionality."""

import tempfile
from pathlib import Path

import pytest
import yaml

from agdd.mcp import MCPRegistry, MCPRegistryError


class TestMCPRegistryDiscovery:
    """Test cases for MCP server auto-discovery."""

    @pytest.fixture
    def temp_servers_dir(self) -> Path:
        """Create a temporary directory for server configs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_mcp_config(self) -> dict[str, object]:
        """Sample MCP server configuration."""
        return {
            "server_id": "test-mcp",
            "type": "mcp",
            "command": "npx",
            "args": ["-y", "@test/server@1.0.0"],
            "description": "Test MCP server",
            "scopes": ["read:test"],
            "limits": {
                "rate_per_min": 60,
                "timeout_s": 30,
            },
        }

    @pytest.fixture
    def sample_postgres_config(self) -> dict[str, object]:
        """Sample PostgreSQL server configuration."""
        return {
            "server_id": "test-pg",
            "type": "postgres",
            "scopes": ["read:tables"],
            "conn": {
                "url_env": "TEST_PG_URL",
            },
            "limits": {
                "rate_per_min": 120,
                "timeout_s": 20,
            },
        }

    def test_discover_empty_directory(self, temp_servers_dir: Path) -> None:
        """Test discovery with no server configs."""
        registry = MCPRegistry(servers_dir=temp_servers_dir)
        registry.discover_servers()

        assert registry.list_servers() == []

    def test_discover_single_server(
        self,
        temp_servers_dir: Path,
        sample_mcp_config: dict[str, object],
    ) -> None:
        """Test discovery of a single MCP server."""
        config_file = temp_servers_dir / "test.yaml"
        with open(config_file, "w") as f:
            yaml.dump(sample_mcp_config, f)

        registry = MCPRegistry(servers_dir=temp_servers_dir)
        registry.discover_servers()

        servers = registry.list_servers()
        assert len(servers) == 1
        assert "test-mcp" in servers

    def test_discover_multiple_servers(
        self,
        temp_servers_dir: Path,
        sample_mcp_config: dict[str, object],
        sample_postgres_config: dict[str, object],
    ) -> None:
        """Test discovery of multiple servers."""
        # Create two config files
        mcp_file = temp_servers_dir / "mcp.yaml"
        with open(mcp_file, "w") as f:
            yaml.dump(sample_mcp_config, f)

        pg_file = temp_servers_dir / "postgres.yaml"
        with open(pg_file, "w") as f:
            yaml.dump(sample_postgres_config, f)

        registry = MCPRegistry(servers_dir=temp_servers_dir)
        registry.discover_servers()

        servers = registry.list_servers()
        assert len(servers) == 2
        assert "test-mcp" in servers
        assert "test-pg" in servers

    def test_discover_ignores_invalid_configs(
        self,
        temp_servers_dir: Path,
    ) -> None:
        """Test that discovery continues despite invalid configs."""
        # Valid config
        valid_file = temp_servers_dir / "valid.yaml"
        with open(valid_file, "w") as f:
            yaml.dump(
                {
                    "server_id": "valid",
                    "type": "mcp",
                    "command": "test",
                    "args": [],
                },
                f,
            )

        # Invalid config (missing required fields)
        invalid_file = temp_servers_dir / "invalid.yaml"
        with open(invalid_file, "w") as f:
            yaml.dump({"invalid": "config"}, f)

        # Empty config
        empty_file = temp_servers_dir / "empty.yaml"
        with open(empty_file, "w") as f:
            f.write("")

        registry = MCPRegistry(servers_dir=temp_servers_dir)
        registry.discover_servers()

        # Should discover only the valid config
        servers = registry.list_servers()
        assert len(servers) == 1
        assert "valid" in servers

    def test_discover_nonexistent_directory(self) -> None:
        """Test discovery with nonexistent directory."""
        registry = MCPRegistry(servers_dir=Path("/nonexistent/path"))
        # Should not raise, just log warning
        registry.discover_servers()
        assert registry.list_servers() == []

    def test_validate_permissions(
        self,
        temp_servers_dir: Path,
        sample_mcp_config: dict[str, object],
    ) -> None:
        """Test permission validation against discovered servers."""
        config_file = temp_servers_dir / "test.yaml"
        with open(config_file, "w") as f:
            yaml.dump(sample_mcp_config, f)

        registry = MCPRegistry(servers_dir=temp_servers_dir)
        registry.discover_servers()

        # Valid permission
        result = registry.validate_permissions(["mcp:test-mcp"])
        assert result == {"mcp:test-mcp": True}

        # Invalid permission (server doesn't exist)
        result = registry.validate_permissions(["mcp:nonexistent"])
        assert result == {"mcp:nonexistent": False}

        # Mixed permissions
        result = registry.validate_permissions(["mcp:test-mcp", "mcp:nonexistent"])
        assert result == {
            "mcp:test-mcp": True,
            "mcp:nonexistent": False,
        }

        # Invalid format
        result = registry.validate_permissions(["invalid:format"])
        assert result == {"invalid:format": False}


class TestMCPRegistryLifecycle:
    """Test cases for MCP server lifecycle management."""

    @pytest.fixture
    def temp_servers_dir(self) -> Path:
        """Create a temporary directory for server configs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def registry_with_servers(self, temp_servers_dir: Path) -> MCPRegistry:
        """Create a registry with sample server configs."""
        # MCP server config
        mcp_file = temp_servers_dir / "mcp.yaml"
        with open(mcp_file, "w") as f:
            yaml.dump(
                {
                    "server_id": "test-mcp",
                    "type": "mcp",
                    "command": "npx",
                    "args": ["-y", "@test/server"],
                },
                f,
            )

        registry = MCPRegistry(servers_dir=temp_servers_dir)
        registry.discover_servers()
        return registry

    @pytest.mark.asyncio
    async def test_start_unknown_server(
        self,
        registry_with_servers: MCPRegistry,
    ) -> None:
        """Test starting a server that doesn't exist."""
        with pytest.raises(MCPRegistryError, match="not found in registry"):
            await registry_with_servers.start_server("nonexistent")

    @pytest.mark.asyncio
    async def test_stop_nonrunning_server(
        self,
        registry_with_servers: MCPRegistry,
    ) -> None:
        """Test stopping a server that isn't running."""
        # Should not raise, just log
        await registry_with_servers.stop_server("test-mcp")

    def test_list_servers(self, registry_with_servers: MCPRegistry) -> None:
        """Test listing all discovered servers."""
        servers = registry_with_servers.list_servers()
        assert "test-mcp" in servers

    @pytest.mark.asyncio
    async def test_list_running_servers(
        self,
        registry_with_servers: MCPRegistry,
    ) -> None:
        """Test listing only running servers."""
        # Initially no servers running
        assert registry_with_servers.list_running_servers() == []

        # Note: We can't actually start the MCP server in tests
        # without a real MCP server implementation, so we just
        # verify the API works

    def test_get_tools_from_nonexistent_server(
        self,
        registry_with_servers: MCPRegistry,
    ) -> None:
        """Test getting tools from a server that doesn't exist."""
        tools = registry_with_servers.get_tools("nonexistent")
        assert tools == []

    def test_get_tools_from_stopped_server(
        self,
        registry_with_servers: MCPRegistry,
    ) -> None:
        """Test getting tools from a stopped server."""
        tools = registry_with_servers.get_tools("test-mcp")
        assert tools == []  # Server not started yet
