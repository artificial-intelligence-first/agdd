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
from collections.abc import Mapping, Sequence
from typing import Any, Callable, Dict, List, Optional, cast

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
        # Default to package directory (parent of agdd module) rather than CWD
        # so registry works regardless of where the process is run from
        if base_path is None:
            base_path = Path(__file__).resolve().parents[1]
        self.base_path = base_path
        self._agent_cache: Dict[str, AgentDescriptor] = {}
        self._skill_cache: Dict[str, SkillDescriptor] = {}

    @staticmethod
    def _ensure_dict(value: Any) -> Dict[str, Any]:
        if isinstance(value, Mapping):
            return {str(key): val for key, val in value.items()}
        return {}

    @staticmethod
    def _parse_contracts(value: Any) -> Dict[str, str]:
        if not isinstance(value, Mapping):
            return {}
        result: Dict[str, str] = {}
        for key, raw in value.items():
            if isinstance(key, str) and isinstance(raw, str):
                result[key] = raw
        return result

    @staticmethod
    def _parse_depends_on(value: Any) -> Dict[str, List[str]]:
        if not isinstance(value, Mapping):
            return {}
        result: Dict[str, List[str]] = {}
        for key, raw in value.items():
            if not isinstance(key, str):
                continue
            items: List[str] = []
            if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
                items = [str(item) for item in raw if isinstance(item, str)]
            result[key] = items
        return result

    @staticmethod
    def _parse_permissions(value: Any) -> List[str]:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [str(item) for item in value if isinstance(item, str)]
        return []

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
                    raw = yaml.safe_load(f)

                if raw is None:
                    raw = {}
                if not isinstance(raw, Mapping):
                    raise ValueError(f"Agent descriptor at {agent_yaml_path} must be a mapping")
                data = dict(raw)

                descriptor = AgentDescriptor(
                    slug=str(data.get("slug", slug)),
                    name=str(data.get("name", slug)),
                    role=str(data.get("role", role_dir)),
                    version=str(data.get("version", "0.0.0")),
                    entrypoint=str(data.get("entrypoint", "")),
                    depends_on=self._parse_depends_on(data.get("depends_on", {})),
                    contracts=self._parse_contracts(data.get("contracts", {})),
                    risk_class=str(data.get("risk_class", "low")),
                    budgets=self._ensure_dict(data.get("budgets", {})),
                    observability=self._ensure_dict(data.get("observability", {})),
                    evaluation=self._ensure_dict(data.get("evaluation", {})),
                    raw=dict(data),
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
            raw = yaml.safe_load(f)

        if raw is None:
            raw = {}
        if not isinstance(raw, Mapping):
            raise ValueError(f"Skills registry at {registry_path} must be a mapping")

        skills = raw.get("skills", [])
        if not isinstance(skills, Sequence):
            raise ValueError(f"'skills' must be a sequence in {registry_path}")

        for skill_data in skills:
            if not isinstance(skill_data, Mapping):
                continue
            if skill_data.get("id") == skill_id:
                descriptor = SkillDescriptor(
                    id=str(skill_data.get("id", skill_id)),
                    version=str(skill_data.get("version", "0.0.0")),
                    entrypoint=str(skill_data.get("entrypoint", "")),
                    permissions=self._parse_permissions(skill_data.get("permissions", [])),
                    raw=dict(skill_data),
                )
                self._skill_cache[skill_id] = descriptor
                return descriptor

        raise ValueError(f"Skill '{skill_id}' not found in {registry_path}")

    def resolve_entrypoint(self, entrypoint: str) -> Callable[..., Any]:
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

        attr = getattr(module, callable_name)
        if not callable(attr):
            raise TypeError(f"Entrypoint '{callable_name}' in {module_path} is not callable")
        return cast(Callable[..., Any], attr)

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
            raw = yaml.safe_load(f)

        if raw is None:
            raw = {}
        if not isinstance(raw, Mapping):
            raise ValueError(f"Agent registry at {registry_path} must be a mapping")

        tasks = raw.get("tasks", [])
        for task_data in tasks:
            if not isinstance(task_data, Mapping):
                continue
            if task_data.get("id") == task_id:
                default_agent_raw = task_data.get("default", "")
                if not isinstance(default_agent_raw, str):
                    raise ValueError(f"Task '{task_id}' default reference must be a string")
                default_agent = default_agent_raw
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
