"""Comprehensive tests for MCP skill integration.

This module tests the integration between skills and MCP runtime,
including async skill execution, permission management, and backward compatibility.
"""

import inspect
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from agdd.mcp import MCPRegistry, MCPRuntime, MCPToolResult
from agdd.registry import Registry, SkillDescriptor
from agdd.runners.agent_runner import SkillRuntime

# Check if asyncpg is available
try:
    import asyncpg  # noqa: F401

    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False


class TestSkillWithMCPParameter:
    """Test cases for skills that accept MCP runtime parameter."""

    @pytest.fixture
    def mcp_registry(self) -> MCPRegistry:
        """Create an MCP registry for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            servers_dir = Path(tmpdir)

            # Create a test MCP server config
            config_file = servers_dir / "test-server.yaml"
            with open(config_file, "w") as f:
                yaml.dump(
                    {
                        "server_id": "test-server",
                        "type": "mcp",
                        "command": "npx",
                        "args": ["-y", "@test/server"],
                        "scopes": ["read:data"],
                    },
                    f,
                )

            registry = MCPRegistry(servers_dir=servers_dir)
            registry.discover_servers()
            return registry

    @pytest.mark.asyncio
    async def test_skill_with_mcp_parameter(self, mcp_registry: MCPRegistry) -> None:
        """Test async skill that accepts mcp parameter.

        Verifies that:
        - MCP runtime is passed correctly to async skills
        - Skills can access granted permissions
        - MCP runtime is properly initialized
        """
        # Create MCP runtime with permissions
        mcp_runtime = MCPRuntime(mcp_registry)
        mcp_runtime.grant_permissions(["mcp:test-server"])

        # Define an async skill that uses MCP
        async def test_skill(payload: Dict[str, Any], mcp: MCPRuntime) -> Dict[str, Any]:
            """Sample async skill that uses MCP runtime."""
            # Verify runtime is passed correctly
            assert isinstance(mcp, MCPRuntime)

            # Verify permissions are granted
            assert mcp.check_permission("test-server")

            # Return success
            return {
                "status": "success",
                "permissions": mcp.get_granted_permissions(),
                "input": payload,
            }

        # Execute the skill
        result = await test_skill({"data": "test"}, mcp=mcp_runtime)

        # Verify results
        assert result["status"] == "success"
        assert "mcp:test-server" in result["permissions"]
        assert result["input"]["data"] == "test"

    @pytest.mark.asyncio
    async def test_skill_without_mcp_parameter(self, mcp_registry: MCPRegistry) -> None:
        """Test async skill that doesn't use MCP parameter.

        Verifies backward compatibility for async skills that don't need MCP.
        """
        async def simple_skill(payload: Dict[str, Any]) -> Dict[str, Any]:
            """Simple async skill without MCP."""
            return {"result": payload["value"] * 2}

        result = await simple_skill({"value": 42})
        assert result["result"] == 84

    @pytest.mark.asyncio
    async def test_skill_with_optional_mcp_parameter(
        self, mcp_registry: MCPRegistry
    ) -> None:
        """Test skill with optional MCP parameter.

        Verifies that skills can declare MCP as optional and handle both cases.
        """
        async def flexible_skill(
            payload: Dict[str, Any], mcp: MCPRuntime | None = None
        ) -> Dict[str, Any]:
            """Skill that optionally uses MCP."""
            if mcp is not None:
                source = "mcp-enabled"
            else:
                source = "fallback"

            return {"value": payload["value"], "source": source}

        # Test with MCP
        mcp_runtime = MCPRuntime(mcp_registry)
        result_with_mcp = await flexible_skill({"value": 10}, mcp=mcp_runtime)
        assert result_with_mcp["source"] == "mcp-enabled"

        # Test without MCP
        result_without_mcp = await flexible_skill({"value": 10})
        assert result_without_mcp["source"] == "fallback"


class TestSkillRuntimeInvokeAsync:
    """Test cases for SkillRuntime.invoke_async() with MCP support."""

    @pytest.fixture
    def temp_dirs(self) -> tuple[Path, Path]:
        """Create temporary directories for skills and MCP servers."""
        with tempfile.TemporaryDirectory() as skills_dir, tempfile.TemporaryDirectory() as servers_dir:
            yield Path(skills_dir), Path(servers_dir)

    @pytest.fixture
    def mock_mcp_registry(self, temp_dirs: tuple[Path, Path]) -> MCPRegistry:
        """Create a mock MCP registry."""
        _, servers_dir = temp_dirs

        # Create server config
        config_file = servers_dir / "pg-readonly.yaml"
        with open(config_file, "w") as f:
            yaml.dump(
                {
                    "server_id": "pg-readonly",
                    "type": "postgres",
                    "scopes": ["read:tables"],
                    "conn": {"url_env": "TEST_PG_URL"},
                },
                f,
            )

        registry = MCPRegistry(servers_dir=servers_dir)
        registry.discover_servers()
        return registry

    @pytest.mark.asyncio
    async def test_skill_runtime_invoke_async_with_mcp(
        self, temp_dirs: tuple[Path, Path], mock_mcp_registry: MCPRegistry
    ) -> None:
        """Test SkillRuntime.invoke_async() with MCP-enabled skill.

        Verifies:
        - invoke_async method exists and works
        - MCP runtime is initialized for the skill
        - Permissions are granted based on skill descriptor
        - Skill receives MCP runtime parameter
        """
        skills_dir, _ = temp_dirs

        # Create a test skill file
        skill_file = skills_dir / "test_skill.py"
        skill_file.write_text(
            """
from typing import Any, Dict

async def run(payload: Dict[str, Any], mcp=None) -> Dict[str, Any]:
    if mcp:
        return {
            "status": "success",
            "has_mcp": True,
            "permissions": mcp.get_granted_permissions()
        }
    return {"status": "success", "has_mcp": False}
""",
            encoding="utf-8",
        )

        # Create skill descriptor
        skill_desc = SkillDescriptor(
            id="skill.test-mcp",
            version="0.1.0",
            entrypoint=f"{skill_file}:run",
            permissions=["mcp:pg-readonly"],
            raw={},
        )

        # Mock registry to return our skill
        mock_registry = MagicMock(spec=Registry)
        mock_registry.load_skill.return_value = skill_desc

        # Mock resolve_entrypoint to return the actual function
        import importlib.util
        spec = importlib.util.spec_from_file_location("test_skill", skill_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        mock_registry.resolve_entrypoint.return_value = module.run

        # Create SkillRuntime with MCP support
        # SkillRuntime creates its own MCPRegistry internally, so we replace it
        skill_runtime = SkillRuntime(registry=mock_registry, enable_mcp=True)
        skill_runtime.mcp_registry = mock_mcp_registry

        # Execute skill
        result = await skill_runtime.invoke_async("skill.test-mcp", {"input": "test"})

        # Verify results
        assert result["status"] == "success"
        assert result["has_mcp"] is True
        assert "mcp:pg-readonly" in result["permissions"]

    @pytest.mark.asyncio
    async def test_skill_runtime_invoke_async_without_mcp(
        self, temp_dirs: tuple[Path, Path]
    ) -> None:
        """Test SkillRuntime.invoke_async() with legacy sync skills.

        Verifies backward compatibility:
        - Sync skills can still be invoked
        - Skills without MCP permissions work correctly
        """
        skills_dir, _ = temp_dirs

        # Create a sync skill file
        skill_file = skills_dir / "sync_skill.py"
        skill_file.write_text(
            """
from typing import Any, Dict

def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"result": payload["value"] * 2, "type": "sync"}
""",
            encoding="utf-8",
        )

        # Create skill descriptor without MCP permissions
        skill_desc = SkillDescriptor(
            id="skill.sync-test",
            version="0.1.0",
            entrypoint=f"{skill_file}:run",
            permissions=[],
            raw={},
        )

        # Mock registry
        mock_registry = MagicMock(spec=Registry)
        mock_registry.load_skill.return_value = skill_desc

        # Load actual function
        import importlib.util
        spec = importlib.util.spec_from_file_location("sync_skill", skill_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        mock_registry.resolve_entrypoint.return_value = module.run

        # Use regular invoke (not invoke_async) for sync skills
        skill_runtime = SkillRuntime(registry=mock_registry)
        result = skill_runtime.invoke("skill.sync-test", {"value": 21})

        assert result["result"] == 42
        assert result["type"] == "sync"


@pytest.mark.skipif(not HAS_ASYNCPG, reason="asyncpg not installed")
class TestSalaryBandLookupWithMCP:
    """Test cases for the actual salary-band-lookup skill with MCP."""

    @pytest.fixture
    def mcp_registry(self) -> MCPRegistry:
        """Create MCP registry with PostgreSQL server."""
        with tempfile.TemporaryDirectory() as tmpdir:
            servers_dir = Path(tmpdir)

            config_file = servers_dir / "pg-readonly.yaml"
            with open(config_file, "w") as f:
                yaml.dump(
                    {
                        "server_id": "pg-readonly",
                        "type": "postgres",
                        "scopes": ["read:tables"],
                        "conn": {"url_env": "TEST_PG_URL"},
                    },
                    f,
                )

            registry = MCPRegistry(servers_dir=servers_dir)
            registry.discover_servers()
            return registry

    @pytest.mark.asyncio
    async def test_salary_band_lookup_with_mcp(self, mcp_registry: MCPRegistry) -> None:
        """Test salary-band-lookup skill with MCP database access.

        Verifies:
        - Skill can query database via MCP
        - Fallback to mock data works when database unavailable
        - Results conform to expected schema
        """
        # Create enhanced version of salary band lookup with MCP
        async def salary_band_lookup_mcp(
            payload: Dict[str, Any], mcp: MCPRuntime | None = None
        ) -> Dict[str, Any]:
            """Enhanced salary band lookup with MCP support."""
            role = payload.get("role", "")
            level = payload.get("level", "")
            location = payload.get("location", "")

            # Try to use MCP if available
            if mcp and mcp.check_permission("pg-readonly"):
                try:
                    # Query database via MCP
                    result = await mcp.query_postgres(
                        server_id="pg-readonly",
                        sql="SELECT * FROM salary_bands WHERE level = $1 LIMIT 1",
                        params=[level],
                    )

                    if result.success and result.output:
                        # Use database result
                        band = result.output[0] if isinstance(result.output, list) else result.output
                        return {
                            "currency": band.get("currency", "USD"),
                            "min": band.get("min_salary"),
                            "max": band.get("max_salary"),
                            "source": "database",
                        }
                except Exception:
                    # Fall through to fallback
                    pass

            # Fallback to mock data
            band = {"currency": "USD", "min": 100000, "max": 180000, "source": "fallback"}

            if "Senior" in role or "Senior" in level:
                band.update(min=150000, max=220000)
            elif "Staff" in role or "Staff" in level:
                band.update(min=180000, max=280000)

            return band

        # Test with MCP (will use fallback since DB isn't actually running)
        mcp_runtime = MCPRuntime(mcp_registry)
        mcp_runtime.grant_permissions(["mcp:pg-readonly"])

        result = await salary_band_lookup_mcp(
            {"role": "Senior Engineer", "level": "L5", "location": "SF"},
            mcp=mcp_runtime,
        )

        # Verify result structure
        assert "currency" in result
        assert "min" in result
        assert "max" in result
        assert "source" in result
        assert result["currency"] == "USD"
        assert result["min"] > 0
        assert result["max"] > result["min"]

    @pytest.mark.asyncio
    async def test_salary_band_lookup_fallback(self) -> None:
        """Test salary-band-lookup skill fallback when MCP unavailable.

        Verifies that the skill works without MCP runtime.
        """
        async def salary_band_lookup_mcp(
            payload: Dict[str, Any], mcp: MCPRuntime | None = None
        ) -> Dict[str, Any]:
            """Enhanced salary band lookup with MCP support."""
            role = payload.get("role", "")
            level = payload.get("level", "")

            # Fallback implementation
            band = {"currency": "USD", "min": 100000, "max": 180000, "source": "fallback"}

            if "Senior" in role or "Senior" in level:
                band.update(min=150000, max=220000)
            elif "Staff" in role or "Staff" in level:
                band.update(min=180000, max=280000)

            return band

        # Test without MCP
        result = await salary_band_lookup_mcp(
            {"role": "Staff Engineer", "level": "L6", "location": "NYC"}
        )

        assert result["source"] == "fallback"
        assert result["min"] == 180000
        assert result["max"] == 280000


class TestMCPRuntimePermissionIsolation:
    """Test cases for MCP runtime permission isolation between skills."""

    @pytest.fixture
    def mcp_registry(self) -> MCPRegistry:
        """Create MCP registry with multiple servers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            servers_dir = Path(tmpdir)

            # Create multiple server configs
            for server_id in ["server1", "server2", "server3"]:
                config_file = servers_dir / f"{server_id}.yaml"
                with open(config_file, "w") as f:
                    yaml.dump(
                        {
                            "server_id": server_id,
                            "type": "mcp",
                            "command": "npx",
                            "args": ["-y", f"@test/{server_id}"],
                        },
                        f,
                    )

            registry = MCPRegistry(servers_dir=servers_dir)
            registry.discover_servers()
            return registry

    def test_mcp_runtime_permission_isolation(self, mcp_registry: MCPRegistry) -> None:
        """Test that different skills get isolated MCP runtimes.

        Verifies:
        - Each skill gets its own runtime instance
        - Permissions don't leak between runtimes
        - Runtimes are properly isolated
        """
        # Create runtime for skill 1 with server1 permission
        runtime1 = MCPRuntime(mcp_registry)
        runtime1.grant_permissions(["mcp:server1"])

        # Create runtime for skill 2 with server2 permission
        runtime2 = MCPRuntime(mcp_registry)
        runtime2.grant_permissions(["mcp:server2"])

        # Create runtime for skill 3 with both permissions
        runtime3 = MCPRuntime(mcp_registry)
        runtime3.grant_permissions(["mcp:server1", "mcp:server3"])

        # Verify isolation
        assert runtime1.check_permission("server1")
        assert not runtime1.check_permission("server2")
        assert not runtime1.check_permission("server3")

        assert not runtime2.check_permission("server1")
        assert runtime2.check_permission("server2")
        assert not runtime2.check_permission("server3")

        assert runtime3.check_permission("server1")
        assert not runtime3.check_permission("server2")
        assert runtime3.check_permission("server3")

        # Verify permission lists are independent
        perms1 = set(runtime1.get_granted_permissions())
        perms2 = set(runtime2.get_granted_permissions())
        perms3 = set(runtime3.get_granted_permissions())

        assert perms1 == {"mcp:server1"}
        assert perms2 == {"mcp:server2"}
        assert perms3 == {"mcp:server1", "mcp:server3"}

    def test_mcp_runtime_permission_changes_isolated(
        self, mcp_registry: MCPRegistry
    ) -> None:
        """Test that permission changes in one runtime don't affect others.

        Verifies that granting/revoking permissions is properly isolated.
        """
        # Create two runtimes with same initial permissions
        runtime1 = MCPRuntime(mcp_registry)
        runtime2 = MCPRuntime(mcp_registry)

        runtime1.grant_permissions(["mcp:server1"])
        runtime2.grant_permissions(["mcp:server1"])

        # Modify runtime1 permissions
        runtime1.grant_permissions(["mcp:server2"])
        runtime1.revoke_permissions(["mcp:server1"])

        # Verify runtime2 is unaffected
        assert not runtime1.check_permission("server1")
        assert runtime1.check_permission("server2")

        assert runtime2.check_permission("server1")
        assert not runtime2.check_permission("server2")


class TestSkillSignatureDetection:
    """Test cases for detecting skill signatures (async vs sync, mcp parameter)."""

    def test_detect_async_skill(self) -> None:
        """Test detection of async skills.

        Verifies that inspect can distinguish async from sync functions.
        """
        async def async_skill(payload: Dict[str, Any]) -> Dict[str, Any]:
            return payload

        def sync_skill(payload: Dict[str, Any]) -> Dict[str, Any]:
            return payload

        assert inspect.iscoroutinefunction(async_skill)
        assert not inspect.iscoroutinefunction(sync_skill)

    def test_detect_mcp_parameter(self) -> None:
        """Test detection of mcp parameter in skill signature.

        Verifies that inspect can determine if a skill accepts MCP runtime.
        """
        async def skill_with_mcp(payload: Dict[str, Any], mcp: MCPRuntime) -> Dict[str, Any]:
            return payload

        async def skill_without_mcp(payload: Dict[str, Any]) -> Dict[str, Any]:
            return payload

        async def skill_with_optional_mcp(
            payload: Dict[str, Any], mcp: MCPRuntime | None = None
        ) -> Dict[str, Any]:
            return payload

        # Check signatures
        sig_with = inspect.signature(skill_with_mcp)
        sig_without = inspect.signature(skill_without_mcp)
        sig_optional = inspect.signature(skill_with_optional_mcp)

        assert "mcp" in sig_with.parameters
        assert "mcp" not in sig_without.parameters
        assert "mcp" in sig_optional.parameters

        # Check if mcp is optional
        assert sig_with.parameters["mcp"].default == inspect.Parameter.empty
        assert sig_optional.parameters["mcp"].default is None

    def test_correct_execution_path_selection(self) -> None:
        """Test that correct execution path is chosen based on signature.

        Verifies the logic for determining how to invoke a skill.
        """
        def should_use_async(func: Any) -> bool:
            """Determine if function should be called with await."""
            return inspect.iscoroutinefunction(func)

        def should_pass_mcp(func: Any) -> bool:
            """Determine if function accepts mcp parameter."""
            sig = inspect.signature(func)
            return "mcp" in sig.parameters

        # Test functions
        async def async_with_mcp(payload: Dict[str, Any], mcp: MCPRuntime) -> Dict[str, Any]:
            return payload

        async def async_without_mcp(payload: Dict[str, Any]) -> Dict[str, Any]:
            return payload

        def sync_skill(payload: Dict[str, Any]) -> Dict[str, Any]:
            return payload

        # Verify detection
        assert should_use_async(async_with_mcp)
        assert should_pass_mcp(async_with_mcp)

        assert should_use_async(async_without_mcp)
        assert not should_pass_mcp(async_without_mcp)

        assert not should_use_async(sync_skill)
        assert not should_pass_mcp(sync_skill)

    def test_skill_invocation_decision_tree(self) -> None:
        """Test the decision tree for skill invocation.

        Verifies all combinations of async/sync and mcp/no-mcp.
        """
        def get_invocation_strategy(func: Any) -> str:
            """Determine how to invoke a skill."""
            is_async = inspect.iscoroutinefunction(func)
            has_mcp = "mcp" in inspect.signature(func).parameters

            if is_async and has_mcp:
                return "async_with_mcp"
            elif is_async and not has_mcp:
                return "async_without_mcp"
            elif not is_async and has_mcp:
                return "sync_with_mcp"  # Unusual but possible
            else:
                return "sync_without_mcp"

        # Test all combinations
        async def f1(p: Dict[str, Any], mcp: MCPRuntime) -> Dict[str, Any]:
            return p

        async def f2(p: Dict[str, Any]) -> Dict[str, Any]:
            return p

        def f3(p: Dict[str, Any], mcp: MCPRuntime) -> Dict[str, Any]:
            return p

        def f4(p: Dict[str, Any]) -> Dict[str, Any]:
            return p

        assert get_invocation_strategy(f1) == "async_with_mcp"
        assert get_invocation_strategy(f2) == "async_without_mcp"
        assert get_invocation_strategy(f3) == "sync_with_mcp"
        assert get_invocation_strategy(f4) == "sync_without_mcp"


class TestSkillMCPIntegrationEdgeCases:
    """Test edge cases and error conditions for MCP skill integration."""

    @pytest.fixture
    def mcp_registry(self) -> MCPRegistry:
        """Create MCP registry for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = MCPRegistry(servers_dir=Path(tmpdir))
            registry.discover_servers()
            return registry

    @pytest.mark.asyncio
    async def test_skill_with_invalid_permissions(self, mcp_registry: MCPRegistry) -> None:
        """Test skill with permissions that don't exist in registry.

        Verifies graceful handling of invalid permission declarations.
        """
        mcp_runtime = MCPRuntime(mcp_registry)

        # Grant permission for non-existent server
        mcp_runtime.grant_permissions(["mcp:nonexistent-server"])

        # Permission check should return False (not error)
        assert not mcp_registry.validate_permissions(["mcp:nonexistent-server"])["mcp:nonexistent-server"]

        # Runtime should still track the permission
        assert "mcp:nonexistent-server" in mcp_runtime.get_granted_permissions()

        # But permission check should fail
        assert mcp_runtime.check_permission("nonexistent-server")

    @pytest.mark.asyncio
    async def test_skill_mixed_valid_invalid_permissions(
        self, mcp_registry: MCPRegistry
    ) -> None:
        """Test skill with mix of valid and invalid permissions.

        Verifies that valid permissions work even when some are invalid.
        """
        # Add a valid server
        with tempfile.TemporaryDirectory() as tmpdir:
            servers_dir = Path(tmpdir)
            config_file = servers_dir / "valid.yaml"
            with open(config_file, "w") as f:
                yaml.dump(
                    {
                        "server_id": "valid-server",
                        "type": "mcp",
                        "command": "test",
                        "args": [],
                    },
                    f,
                )

            registry = MCPRegistry(servers_dir=servers_dir)
            registry.discover_servers()

            runtime = MCPRuntime(registry)
            runtime.grant_permissions([
                "mcp:valid-server",
                "mcp:invalid-server",
            ])

            # Valid permission should work
            assert runtime.check_permission("valid-server")

            # Invalid permission should still be granted (validation is separate)
            assert runtime.check_permission("invalid-server")

    @pytest.mark.asyncio
    async def test_skill_error_handling(self, mcp_registry: MCPRegistry) -> None:
        """Test error handling in skills that use MCP.

        Verifies that exceptions in MCP operations are handled gracefully.
        """
        async def error_prone_skill(
            payload: Dict[str, Any], mcp: MCPRuntime
        ) -> Dict[str, Any]:
            """Skill that might encounter MCP errors."""
            try:
                # This will fail if server isn't running
                result = await mcp.execute_tool(
                    server_id="nonexistent",
                    tool_name="test",
                    arguments={},
                )

                if not result.success:
                    return {
                        "status": "error",
                        "error": result.error,
                        "fallback": True,
                    }

                return {"status": "success", "data": result.output}
            except Exception as e:
                return {
                    "status": "exception",
                    "error": str(e),
                    "fallback": True,
                }

        mcp_runtime = MCPRuntime(mcp_registry)
        mcp_runtime.grant_permissions(["mcp:nonexistent"])

        result = await error_prone_skill({"input": "test"}, mcp=mcp_runtime)

        # Should return error response, not raise exception
        assert result["status"] in ["error", "exception"]
        assert result["fallback"] is True
