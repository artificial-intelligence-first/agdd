"""Routing policy definitions for task-to-provider mapping with execution strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml  # type: ignore[import-untyped]


@dataclass(frozen=True)
class Route:
    """
    Route definition mapping task types to providers with execution strategies.

    Attributes:
        task_type: Task type identifier (e.g., "offer-orchestration")
        provider: LLM provider identifier (e.g., "openai", "anthropic")
        model: Model identifier (e.g., "gpt-4", "claude-3-5-sonnet")
        use_batch: Enable batch API for cost optimization
        use_cache: Enable prompt caching for repeated requests
        structured_output: Enable structured output mode
        moderation: Enable content moderation
        priority: Route priority (higher = higher priority)
        metadata: Additional route metadata
    """

    task_type: str
    provider: str
    model: str
    use_batch: bool = False
    use_cache: bool = False
    structured_output: bool = False
    moderation: bool = False
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoutingPolicy:
    """
    Routing policy containing multiple routes with fallback logic.

    Attributes:
        name: Policy name (e.g., "default", "cost-optimized")
        description: Policy description
        routes: List of routes ordered by priority
    """

    name: str
    description: str
    routes: list[Route]

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> RoutingPolicy:
        """
        Load routing policy from YAML file.

        Args:
            yaml_path: Path to YAML policy file

        Returns:
            RoutingPolicy instance

        Raises:
            FileNotFoundError: If YAML file not found
            ValueError: If YAML structure is invalid
        """
        if not yaml_path.exists():
            raise FileNotFoundError(f"Routing policy not found: {yaml_path}")

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Routing policy must be a mapping in {yaml_path}")

        name = str(data.get("name", yaml_path.stem))
        description = str(data.get("description", ""))
        routes_data = data.get("routes", [])

        if not isinstance(routes_data, list):
            raise ValueError(f"'routes' must be a list in {yaml_path}")

        routes: list[Route] = []
        for route_data in routes_data:
            if not isinstance(route_data, dict):
                continue

            route = Route(
                task_type=str(route_data.get("task_type", "*")),
                provider=str(route_data.get("provider", "")),
                model=str(route_data.get("model", "")),
                use_batch=bool(route_data.get("use_batch", False)),
                use_cache=bool(route_data.get("use_cache", False)),
                structured_output=bool(route_data.get("structured_output", False)),
                moderation=bool(route_data.get("moderation", False)),
                priority=int(route_data.get("priority", 0)),
                metadata=dict(route_data.get("metadata", {})),
            )
            routes.append(route)

        # Sort by priority (descending)
        routes.sort(key=lambda r: r.priority, reverse=True)

        return cls(name=name, description=description, routes=routes)

    def get_route(
        self, task_type: str, overrides: Optional[dict[str, Any]] = None
    ) -> Optional[Route]:
        """
        Get route for task type with optional overrides.

        Args:
            task_type: Task type identifier
            overrides: Optional overrides for route attributes

        Returns:
            Matching Route or None if not found
        """
        from fnmatch import fnmatch

        # Find matching route (exact match first, then pattern match)
        matched_route: Optional[Route] = None
        for route in self.routes:
            if route.task_type == task_type:
                matched_route = route
                break
            if fnmatch(task_type, route.task_type):
                matched_route = route
                break

        if matched_route is None:
            return None

        # Apply overrides if provided
        if overrides:
            route_dict: dict[str, Any] = {
                "task_type": matched_route.task_type,
                "provider": matched_route.provider,
                "model": matched_route.model,
                "use_batch": matched_route.use_batch,
                "use_cache": matched_route.use_cache,
                "structured_output": matched_route.structured_output,
                "moderation": matched_route.moderation,
                "priority": matched_route.priority,
                "metadata": matched_route.metadata.copy(),
            }
            route_dict.update(overrides)
            return Route(
                task_type=str(route_dict["task_type"]),
                provider=str(route_dict["provider"]),
                model=str(route_dict["model"]),
                use_batch=bool(route_dict["use_batch"]),
                use_cache=bool(route_dict["use_cache"]),
                structured_output=bool(route_dict["structured_output"]),
                moderation=bool(route_dict["moderation"]),
                priority=int(route_dict["priority"]),
                metadata=dict(route_dict.get("metadata", {})),
            )

        return matched_route
