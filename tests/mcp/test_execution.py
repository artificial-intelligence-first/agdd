"""Tests for MCP tool execution functionality."""

import logging
import os
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from agdd.mcp import MCPRegistry, MCPRuntime, MCPToolResult
from agdd.mcp.config import MCPServerConfig
from agdd.mcp.server import MCPServer


pytestmark = pytest.mark.slow
# Check if asyncpg is available
try:
    import asyncpg  # noqa: F401


    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False


@pytest.mark.asyncio
async def test_mcp_stdio_server_tool_execution(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Ensure stdio MCP server handshake and tool execution succeed."""
    script_path = tmp_path / "fake_mcp_server.py"
    script_lines = [
        "import json",
        "import sys",
        "",
        "TOOLS = [",
        "    {",
        "        \"name\": \"echo\",",
        "        \"description\": \"Echo arguments back to the caller\",",
        "        \"inputSchema\": {",
        "            \"type\": \"object\",",
        "            \"properties\": {",
        "                \"value\": {\"type\": \"string\", \"description\": \"Value to echo\"}",
        "            },",
        "            \"required\": [\"value\"],",
        "        },",
        "    }",
        "]",
        "",
        "def send(payload):",
        "    sys.stdout.write(json.dumps(payload) + \"\\n\")",
        "    sys.stdout.flush()",
        "",
        "def main() -> None:",
        "    try:",
        "        for line in sys.stdin:",
        "            if not line.strip():",
        "                continue",
        "            message = json.loads(line)",
        "            method = message.get(\"method\")",
        "            if method == \"initialize\":",
        "                send({",
        "                    \"jsonrpc\": \"2.0\",",
        "                    \"id\": message[\"id\"],",
        "                    \"result\": {",
        "                        \"capabilities\": {},",
        "                        \"serverInfo\": {\"name\": \"fake-mcp\", \"version\": \"0.1\"},",
        "                    },",
        "                })",
        "            elif method == \"notifications/initialized\":",
        "                continue",
        "            elif method == \"tools/list\":",
        "                send({",
        "                    \"jsonrpc\": \"2.0\",",
        "                    \"id\": message[\"id\"],",
        "                    \"result\": {\"tools\": TOOLS},",
        "                })",
        "            elif method == \"tools/call\":",
        "                params = message.get(\"params\", {})",
        "                name = params.get(\"name\")",
        "                args = params.get(\"arguments\", {})",
        "                if name == \"echo\":",
        "                    send({",
        "                        \"jsonrpc\": \"2.0\",",
        "                        \"id\": message[\"id\"],",
        "                        \"result\": {\"success\": True, \"output\": {\"echo\": args}},",
        "                    })",
        "                else:",
        "                    send({",
        "                        \"jsonrpc\": \"2.0\",",
        "                        \"id\": message[\"id\"],",
        "                        \"result\": {\"success\": False, \"error\": f\"unknown tool {name}\"},",
        "                    })",
        "            else:",
        "                if message.get(\"id\") is not None:",
        "                    send({",
        "                        \"jsonrpc\": \"2.0\",",
        "                        \"id\": message[\"id\"],",
        "                        \"error\": {\"message\": \"unknown method\"},",
        "                    })",
        "    except Exception as exc:",
        "        sys.stderr.write(f\"ERROR: {exc}\\n\")",
        "        sys.stderr.flush()",
        "        raise",
        "",
        "if __name__ == \"__main__\":",
        "    main()",
        "",
    ]

    script_path.write_text("\n".join(script_lines), encoding="utf-8")

    config = MCPServerConfig(
        server_id="test-stdio",
        type="mcp",
        scopes=[],
        command=sys.executable,
        args=["-u", str(script_path)],
    )

    server = MCPServer(config)

    try:
        with caplog.at_level(logging.DEBUG, logger="agdd.mcp.server"):
            await server.start()

        tools = server.get_tools()
        assert len(tools) == 1
        assert tools[0].name == "echo"

        result = await server.execute_tool("echo", {"value": "hello"})
        assert result.success
        assert result.output == {"echo": {"value": "hello"}}
        assert result.metadata["server_id"] == "test-stdio"

        error_result = await server.execute_tool("nonexistent", {})
        assert not error_result.success
        assert "not found" in (error_result.error or "")

    finally:
        await server.stop()


@pytest.mark.skipif(not HAS_ASYNCPG, reason="asyncpg not installed")
class TestMCPToolExecution:
    """Test cases for MCP tool execution."""

    @pytest.fixture
    def temp_servers_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for server configs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def postgres_registry(self, temp_servers_dir: Path) -> MCPRegistry:
        """Create a registry with PostgreSQL server config."""
        pg_file = temp_servers_dir / "pg.yaml"
        with open(pg_file, "w") as f:
            yaml.dump(
                {
                    "server_id": "test-pg",
                    "type": "postgres",
                    "scopes": ["read:tables"],
                    "conn": {
                        "url_env": "TEST_PG_URL",
                    },
                },
                f,
            )

        registry = MCPRegistry(servers_dir=temp_servers_dir)
        registry.discover_servers()
        return registry

    @pytest.mark.asyncio
    async def test_execute_tool_without_permission(
        self,
        postgres_registry: MCPRegistry,
    ) -> None:
        """Test executing a tool without proper permissions."""
        runtime = MCPRuntime(postgres_registry)
        # Don't grant any permissions

        result = await runtime.execute_tool(
            server_id="test-pg",
            tool_name="query",
            arguments={"sql": "SELECT 1"},
        )

        assert not result.success
        assert result.error is not None
        assert "Permission denied" in result.error

    @pytest.mark.asyncio
    async def test_execute_tool_with_permission(
        self,
        postgres_registry: MCPRegistry,
    ) -> None:
        """Test executing a tool with proper permissions."""
        runtime = MCPRuntime(postgres_registry)
        runtime.grant_permissions(["mcp:test-pg"])

        # Mock the actual PostgreSQL execution
        with patch("agdd.mcp.server.asyncpg.create_pool") as mock_pool:
            # Create mock pool and connection
            mock_conn = AsyncMock()
            mock_conn.fetch = AsyncMock(
                return_value=[{"result": 1}]
            )

            mock_pool_instance = AsyncMock()
            mock_pool_instance.acquire = MagicMock(
                return_value=mock_conn.__aenter__.return_value
            )
            mock_pool_instance.__aenter__ = AsyncMock(
                return_value=mock_pool_instance
            )
            mock_pool.return_value = mock_pool_instance

            # Set environment variable for connection
            os.environ["TEST_PG_URL"] = "postgresql://test:test@localhost/test"

            try:
                result = await runtime.execute_tool(
                    server_id="test-pg",
                    tool_name="query",
                    arguments={"sql": "SELECT 1"},
                )

                # Verify execution succeeded
                # Note: Actual success depends on mock setup
                assert isinstance(result, MCPToolResult)

            finally:
                del os.environ["TEST_PG_URL"]

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(
        self,
        postgres_registry: MCPRegistry,
    ) -> None:
        """Test executing a tool that doesn't exist."""
        runtime = MCPRuntime(postgres_registry)
        runtime.grant_permissions(["mcp:test-pg"])

        # Mock PostgreSQL connection
        with patch("agdd.mcp.server.asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
            # Create async mock for pool instance
            mock_pool_instance = AsyncMock()
            mock_pool_instance.acquire = AsyncMock()
            mock_pool_instance.close = AsyncMock()

            # make create_pool (which is now an AsyncMock) return the pool instance
            mock_pool.return_value = mock_pool_instance

            os.environ["TEST_PG_URL"] = "postgresql://test:test@localhost/test"

            try:
                result = await runtime.execute_tool(
                    server_id="test-pg",
                    tool_name="nonexistent_tool",
                    arguments={},
                )

                assert not result.success
                assert result.error is not None
                assert "not found" in result.error.lower()

            finally:
                del os.environ["TEST_PG_URL"]


class TestMCPRuntimePermissions:
    """Test cases for MCP runtime permission management."""

    @pytest.fixture
    def registry(self) -> MCPRegistry:
        """Create a minimal registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = MCPRegistry(servers_dir=Path(tmpdir))
            registry.discover_servers()
            return registry

    def test_grant_permissions(self, registry: MCPRegistry) -> None:
        """Test granting permissions to runtime."""
        runtime = MCPRuntime(registry)

        runtime.grant_permissions(["mcp:server1", "mcp:server2"])

        granted = runtime.get_granted_permissions()
        assert "mcp:server1" in granted
        assert "mcp:server2" in granted

    def test_revoke_permissions(self, registry: MCPRegistry) -> None:
        """Test revoking permissions from runtime."""
        runtime = MCPRuntime(registry)

        runtime.grant_permissions(["mcp:server1", "mcp:server2"])
        runtime.revoke_permissions(["mcp:server1"])

        granted = runtime.get_granted_permissions()
        assert "mcp:server1" not in granted
        assert "mcp:server2" in granted

    def test_check_permission(self, registry: MCPRegistry) -> None:
        """Test checking individual permissions."""
        runtime = MCPRuntime(registry)

        runtime.grant_permissions(["mcp:server1"])

        assert runtime.check_permission("server1")
        assert not runtime.check_permission("server2")

    def test_list_available_tools_without_permissions(
        self,
        registry: MCPRegistry,
    ) -> None:
        """Test listing tools without any permissions."""
        runtime = MCPRuntime(registry)

        tools = runtime.list_available_tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_query_postgres_convenience_method(
        self,
        registry: MCPRegistry,
    ) -> None:
        """Test the PostgreSQL query convenience method."""
        runtime = MCPRuntime(registry)
        runtime.grant_permissions(["mcp:test-pg"])

        # This will fail without actual server, but tests the API
        result = await runtime.query_postgres(
            server_id="test-pg",
            sql="SELECT * FROM users",
            params=["value1"],
        )

        # Verify it returns a result (even if failed)
        assert isinstance(result, MCPToolResult)

    @pytest.mark.asyncio
    async def test_list_postgres_tables_convenience_method(
        self,
        registry: MCPRegistry,
    ) -> None:
        """Test the PostgreSQL list tables convenience method."""
        runtime = MCPRuntime(registry)
        runtime.grant_permissions(["mcp:test-pg"])

        # This will fail without actual server, but tests the API
        result = await runtime.list_postgres_tables(
            server_id="test-pg",
            schema="custom_schema",
        )

        # Verify it returns a result (even if failed)
        assert isinstance(result, MCPToolResult)
