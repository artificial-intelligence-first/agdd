"""
Registry loader for agents and skills.

Loads agent descriptors from agents/*/agent.yaml and skill definitions
from registry/skills.yaml. Provides resolution of entrypoints and dependencies.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml


@dataclass
class AgentDescriptor:
    """Agent metadata loaded from agent.yaml"""

    slug: str
    name: str
    role: str  # "main" or "sub"
    version: str
    entrypoint: str  # "path/to/module.py:callable"
    depends_on: Dict[str, List[str]]  # {"sub_agents": [...], "skills": [...]}
    contracts: Dict[str, str]  # {"input_schema": "...", "output_schema": "..."}
    risk_class: str
    budgets: Dict[str, Any]
    observability: Dict[str, Any]
    evaluation: Dict[str, Any]
    raw: Dict[str, Any]  # Full YAML content


@dataclass
class SkillDescriptor:
    """Skill metadata loaded from registry/skills.yaml"""

    id: str
    version: str
    entrypoint: str
    permissions: List[str]
    raw: Dict[str, Any]


class Registry:
    """Central registry for agents and skills"""

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path.cwd()
        self._agent_cache: Dict[str, AgentDescriptor] = {}
        self._skill_cache: Dict[str, SkillDescriptor] = {}

    def load_agent(self, slug: str) -> AgentDescriptor:
        """
        Load agent descriptor from agents/{role}/{slug}/agent.yaml

        Args:
            slug: Agent slug (e.g., "offer-orchestrator-mag" or "compensation-advisor-sag")

        Returns:
            AgentDescriptor with parsed metadata

        Raises:
            FileNotFoundError: If agent.yaml not found
            ValueError: If YAML is malformed
        """
        if slug in self._agent_cache:
            return self._agent_cache[slug]

        # Search in agents/main/ and agents/sub/
        for role_dir in ["main", "sub"]:
            agent_yaml_path = (
                self.base_path / "agents" / role_dir / slug / "agent.yaml"
            )
            if agent_yaml_path.exists():
                with open(agent_yaml_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                descriptor = AgentDescriptor(
                    slug=data.get("slug", slug),
                    name=data.get("name", slug),
                    role=data.get("role", role_dir),
                    version=data.get("version", "0.0.0"),
                    entrypoint=data.get("entrypoint", ""),
                    depends_on=data.get("depends_on", {}),
                    contracts=data.get("contracts", {}),
                    risk_class=data.get("risk_class", "low"),
                    budgets=data.get("budgets", {}),
                    observability=data.get("observability", {}),
                    evaluation=data.get("evaluation", {}),
                    raw=data,
                )
                self._agent_cache[slug] = descriptor
                return descriptor

        raise FileNotFoundError(f"Agent '{slug}' not found in agents/main/ or agents/sub/")

    def load_skill(self, skill_id: str) -> SkillDescriptor:
        """
        Load skill descriptor from registry/skills.yaml

        Args:
            skill_id: Skill identifier (e.g., "skill.salary-band-lookup")

        Returns:
            SkillDescriptor with parsed metadata

        Raises:
            FileNotFoundError: If registry/skills.yaml not found
            ValueError: If skill not found in registry
        """
        if skill_id in self._skill_cache:
            return self._skill_cache[skill_id]

        registry_path = self.base_path / "registry" / "skills.yaml"
        if not registry_path.exists():
            raise FileNotFoundError(f"Skills registry not found at {registry_path}")

        with open(registry_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        skills = data.get("skills", [])
        for skill_data in skills:
            if skill_data.get("id") == skill_id:
                descriptor = SkillDescriptor(
                    id=skill_data.get("id", skill_id),
                    version=skill_data.get("version", "0.0.0"),
                    entrypoint=skill_data.get("entrypoint", ""),
                    permissions=skill_data.get("permissions", []),
                    raw=skill_data,
                )
                self._skill_cache[skill_id] = descriptor
                return descriptor

        raise ValueError(f"Skill '{skill_id}' not found in {registry_path}")

    def resolve_entrypoint(self, entrypoint: str) -> Callable:
        """
        Resolve entrypoint string to callable function.

        Args:
            entrypoint: Format "path/to/module.py:function_name"

        Returns:
            Callable function from the module

        Raises:
            ValueError: If entrypoint format is invalid
            ImportError: If module cannot be loaded
            AttributeError: If function not found in module
        """
        if ":" not in entrypoint:
            raise ValueError(f"Invalid entrypoint format: {entrypoint} (expected 'path:callable')")

        module_path_str, callable_name = entrypoint.rsplit(":", 1)
        module_path = self.base_path / module_path_str

        if not module_path.exists():
            raise FileNotFoundError(f"Entrypoint module not found: {module_path}")

        # Dynamic module loading
        spec = importlib.util.spec_from_file_location(f"_agdd_dynamic_{id(module_path)}", module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for {module_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        if not hasattr(module, callable_name):
            raise AttributeError(f"Function '{callable_name}' not found in {module_path}")

        return getattr(module, callable_name)

    def resolve_task(self, task_id: str) -> str:
        """
        Resolve task ID to agent slug from registry/agents.yaml

        Args:
            task_id: Task identifier (e.g., "offer-orchestration")

        Returns:
            Agent slug that handles this task

        Raises:
            ValueError: If task not found
        """
        registry_path = self.base_path / "registry" / "agents.yaml"
        if not registry_path.exists():
            raise FileNotFoundError(f"Agent registry not found at {registry_path}")

        with open(registry_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        tasks = data.get("tasks", [])
        for task_data in tasks:
            if task_data.get("id") == task_id:
                default_agent = task_data.get("default", "")
                # Parse "agdd://main.offer-orchestrator-mag@>=0.1.0" -> "offer-orchestrator-mag"
                if default_agent.startswith("agdd://"):
                    agent_ref = default_agent.replace("agdd://", "").split("@")[0]
                    # Remove role prefix (main./sub.)
                    slug = agent_ref.split(".", 1)[-1]
                    return slug
                return default_agent

        raise ValueError(f"Task '{task_id}' not found in {registry_path}")


# Singleton instance
_registry: Optional[Registry] = None


def get_registry(base_path: Optional[Path] = None) -> Registry:
    """Get or create the global registry instance"""
    global _registry
    if _registry is None or base_path is not None:
        _registry = Registry(base_path=base_path)
    return _registry
