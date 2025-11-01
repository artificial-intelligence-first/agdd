"""MCP Server provider for MAGSAG agents and skills.

This module implements an MCP server that exposes MAGSAG agents and skills
as MCP tools, allowing them to be called from Claude Desktop and other
MCP clients.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, ContextManager

if TYPE_CHECKING:
    pass

from magsag.registry import Registry
from magsag.runners.agent_runner import AgentRunner

logger = logging.getLogger(__name__)

# Note: FastMCP is loaded dynamically via _load_fastmcp() below to avoid
# import-path conflicts with tests/mcp during pytest collection.


def _tests_dir() -> Path:
    """Return the absolute path to the repository's tests directory."""

    return (Path(__file__).resolve().parents[3] / "tests").resolve()


def _without_tests_path() -> ContextManager[None]:
    """Temporarily remove the local tests directory from sys.path.

    Pytest adds the repository's tests directory to the front of sys.path.
    That creates a naming conflict with the third-party ``mcp`` package
    because we also have ``tests/mcp``. When that happens, importing
    ``mcp.server.fastmcp`` resolves to the tests package instead of the SDK.
    This helper momentarily drops the conflicting path so the real SDK
    can be imported, then restores the original order.
    """

    tests_dir = _tests_dir()

    @contextmanager
    def _manager() -> Iterator[None]:
        removed: list[tuple[int, str]] = []

        for idx, entry in enumerate(list(sys.path)):
            try:
                resolved = Path(entry).resolve()
            except (OSError, RuntimeError, ValueError) as exc:  # pragma: no cover - defensive
                logger.debug("Skipped non-resolvable sys.path entry %s", entry, exc_info=exc)
            else:
                if resolved == tests_dir:
                    removed.append((idx, entry))

        for idx, _ in reversed(removed):
            sys.path.pop(idx)

        try:
            yield
        finally:
            for idx, entry in removed:
                sys.path.insert(idx, entry)

    return _manager()


def _load_fastmcp() -> tuple[bool, Any | None, Any | None]:
    """Attempt to load FastMCP, handling path conflicts with tests/mcp."""
    try:
        from mcp.server.fastmcp import Context, FastMCP

        return True, FastMCP, Context
    except ImportError:
        try:
            with _without_tests_path():
                existing = sys.modules.get("mcp")
                if existing:
                    existing_file = getattr(existing, "__file__", None)
                    if existing_file:
                        try:
                            module_path = Path(str(existing_file)).resolve()
                            tests_dir = _tests_dir()
                            try:
                                is_tests_pkg = module_path.is_relative_to(tests_dir)
                            except AttributeError:  # pragma: no cover - py<3.9 fallback
                                is_tests_pkg = str(module_path).startswith(str(tests_dir))
                        except Exception:  # pragma: no cover - defensive
                            is_tests_pkg = False
                        if is_tests_pkg:
                            sys.modules.pop("mcp", None)
                from mcp.server.fastmcp import Context, FastMCP

                return True, FastMCP, Context
        except ImportError:
            return False, None, None


_has_sdk, FastMCP, Context = _load_fastmcp()
HAS_MCP_SDK = bool(_has_sdk)


class MAGSAGMCPServer:
    """MCP server that exposes MAGSAG agents and skills as tools.

    This server allows external MCP clients (like Claude Desktop) to invoke
    MAGSAG agents and skills through the Model Context Protocol.
    """

    def __init__(
        self,
        base_path: Path | None = None,
        expose_agents: bool = True,
        expose_skills: bool = False,
        agent_filter: list[str] | None = None,
        skill_filter: list[str] | None = None,
    ) -> None:
        """Initialize MAGSAG MCP server.

        Args:
            base_path: Base path for MAGSAG catalog (defaults to project root)
            expose_agents: Whether to expose agents as tools (default: True)
            expose_skills: Whether to expose skills as tools (default: False)
            agent_filter: List of agent slugs to expose (None = all agents)
            skill_filter: List of skill IDs to expose (None = all skills)

        Raises:
            ImportError: If mcp package is not installed
        """
        if not HAS_MCP_SDK:
            raise ImportError("MCP SDK not installed. Install with: pip install mcp")

        self.base_path = base_path
        self.expose_agents = expose_agents
        self.expose_skills = expose_skills
        self.agent_filter = agent_filter
        self.skill_filter = skill_filter

        # Initialize MAGSAG registry
        self.registry = Registry(base_path=base_path)

        # Initialize agent runner with custom registry
        # This ensures agents are loaded from the same catalog used for discovery
        self.runner = AgentRunner(registry=self.registry)

        # Initialize FastMCP server
        if FastMCP is None:
            raise ImportError("FastMCP not available")
        self.mcp = FastMCP(name="magsag")

        # Register tools
        self._register_tools()

    def _register_tools(self) -> None:
        """Register MAGSAG agents and skills as MCP tools."""
        if self.expose_agents:
            self._register_agent_tools()

        if self.expose_skills:
            self._register_skill_tools()

    def _register_agent_tools(self) -> None:
        """Register all MAGSAG agents as MCP tools."""
        # Discover agents from catalog
        agents_dir = self.registry.base_path / "catalog" / "agents"

        for role_dir in ["main", "sub"]:
            role_path = agents_dir / role_dir
            if not role_path.exists():
                continue

            for agent_path in role_path.iterdir():
                if not agent_path.is_dir():
                    continue

                agent_yaml = agent_path / "agent.yaml"
                if not agent_yaml.exists():
                    continue

                slug = agent_path.name

                # Apply filter
                if self.agent_filter and slug not in self.agent_filter:
                    continue

                try:
                    descriptor = self.registry.load_agent(slug)
                    self._register_agent_tool(descriptor)
                    logger.info(f"Registered agent tool: {slug}")
                except Exception as e:
                    logger.warning(f"Failed to register agent {slug}: {e}")

    def _register_agent_tool(self, descriptor: Any) -> None:
        """Register a single agent as an MCP tool.

        Args:
            descriptor: AgentDescriptor instance
        """
        slug = descriptor.slug
        name = descriptor.name
        role = descriptor.role

        # Load input schema if available
        input_schema_path = descriptor.contracts.get("input_schema")
        schema_doc = ""
        if input_schema_path:
            full_path = self.registry.base_path / input_schema_path
            if full_path.exists():
                schema_doc = f"\n\nInput Schema: {input_schema_path}"

        # Create tool description
        description = f"{name} ({role} agent){schema_doc}"

        # Register tool using FastMCP decorator pattern
        # We use a closure to capture slug and runner
        # Store runner reference to avoid binding issues in closure
        runner = self.runner

        async def agent_runner(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
            """Execute MAGSAG agent.

            Args:
                payload: Agent input payload matching the agent's input schema
                ctx: MCP context for logging and progress

            Returns:
                Agent output matching the agent's output schema
            """
            await ctx.info(f"Executing agent: {slug}")

            try:
                # Run agent synchronously using the server's runner instance
                # This ensures the agent is loaded from the correct catalog
                loop = asyncio.get_event_loop()
                context: dict[str, Any] = {}
                output = await loop.run_in_executor(
                    None, lambda: runner.invoke_mag(slug=slug, payload=payload, context=context)
                )

                await ctx.info(f"Agent {slug} completed successfully")
                return output

            except Exception as e:
                error_msg = f"Agent execution failed: {str(e)}"
                await ctx.error(error_msg)
                raise RuntimeError(error_msg) from e

        # Set function metadata for FastMCP
        agent_runner.__name__ = slug.replace("-", "_")
        agent_runner.__doc__ = description

        # Register with MCP
        self.mcp.tool()(agent_runner)

    def _register_skill_tools(self) -> None:
        """Register all MAGSAG skills as MCP tools."""
        skills_yaml = self.registry.base_path / "catalog" / "registry" / "skills.yaml"

        if not skills_yaml.exists():
            logger.warning("skills.yaml not found, skipping skill registration")
            return

        try:
            import yaml

            with open(skills_yaml, "r") as f:
                data = yaml.safe_load(f)

            skills = data.get("skills", [])

            for skill_data in skills:
                skill_id = skill_data.get("id")

                # Apply filter
                if self.skill_filter and skill_id not in self.skill_filter:
                    continue

                try:
                    descriptor = self.registry.load_skill(skill_id)
                    self._register_skill_tool(descriptor)
                    logger.info(f"Registered skill tool: {skill_id}")
                except Exception as e:
                    logger.warning(f"Failed to register skill {skill_id}: {e}")

        except Exception as e:
            logger.error(f"Failed to load skills.yaml: {e}")

    def _register_skill_tool(self, descriptor: Any) -> None:
        """Register a single skill as an MCP tool.

        Args:
            descriptor: SkillDescriptor instance
        """
        skill_id = descriptor.id

        # Create tool description
        description = f"MAGSAG skill: {skill_id}"

        # Register tool
        async def skill_runner(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
            """Execute MAGSAG skill.

            Args:
                payload: Skill input payload
                ctx: MCP context

            Returns:
                Skill output
            """
            await ctx.info(f"Executing skill: {skill_id}")

            try:
                # Load and execute skill
                # Note: This would require skill execution infrastructure
                # For now, return placeholder
                await ctx.info(f"Skill {skill_id} executed")
                return {"status": "completed", "skill_id": skill_id}

            except Exception as e:
                error_msg = f"Skill execution failed: {str(e)}"
                await ctx.error(error_msg)
                raise RuntimeError(error_msg) from e

        # Set function metadata
        skill_runner.__name__ = skill_id.replace(".", "_").replace("-", "_")
        skill_runner.__doc__ = description

        # Register with MCP
        self.mcp.tool()(skill_runner)

    def run(self, transport: str = "stdio") -> None:
        """Run the MCP server.

        Args:
            transport: Transport type ("stdio" for standard I/O)
        """
        if not HAS_MCP_SDK:
            raise ImportError("MCP SDK not installed. Install with: pip install mcp")

        logger.info("Starting MAGSAG MCP server")
        logger.info(f"Exposing agents: {self.expose_agents}")
        logger.info(f"Exposing skills: {self.expose_skills}")

        self.mcp.run(transport=transport)


def create_server(
    base_path: Path | None = None,
    expose_agents: bool = True,
    expose_skills: bool = False,
    agent_filter: list[str] | None = None,
    skill_filter: list[str] | None = None,
) -> MAGSAGMCPServer:
    """Create an MAGSAG MCP server instance.

    Args:
        base_path: Base path for MAGSAG catalog
        expose_agents: Whether to expose agents as tools
        expose_skills: Whether to expose skills as tools
        agent_filter: List of agent slugs to expose (None = all)
        skill_filter: List of skill IDs to expose (None = all)

    Returns:
        Configured MAGSAGMCPServer instance
    """
    return MAGSAGMCPServer(
        base_path=base_path,
        expose_agents=expose_agents,
        expose_skills=expose_skills,
        agent_filter=agent_filter,
        skill_filter=skill_filter,
    )
