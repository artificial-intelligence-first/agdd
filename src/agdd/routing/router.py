"""Router for generating execution plans from routing policies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from agdd.routing.policy import Route, RoutingPolicy


@dataclass(frozen=True)
class Plan:
    """
    Execution plan containing provider and execution strategies.

    Attributes:
        task_type: Task type identifier
        provider: LLM provider (e.g., "openai", "anthropic")
        model: Model identifier (e.g., "gpt-4", "claude-3-5-sonnet")
        use_batch: Whether to use batch API
        use_cache: Whether to use prompt caching
        structured_output: Whether to use structured output mode
        moderation: Whether to enable content moderation
        metadata: Additional execution metadata
    """

    task_type: str
    provider: str
    model: str
    use_batch: bool
    use_cache: bool
    structured_output: bool
    moderation: bool
    metadata: dict[str, Any]

    @classmethod
    def from_route(cls, route: Route) -> Plan:
        """
        Create Plan from Route.

        Args:
            route: Route to convert

        Returns:
            Plan instance with copied metadata to prevent shared mutation
        """
        return cls(
            task_type=route.task_type,
            provider=route.provider,
            model=route.model,
            use_batch=route.use_batch,
            use_cache=route.use_cache,
            structured_output=route.structured_output,
            moderation=route.moderation,
            metadata=route.metadata.copy(),
        )


# Default policy instance
_default_policy: Optional[RoutingPolicy] = None


def _get_default_policy() -> RoutingPolicy:
    """Get or load default routing policy."""
    global _default_policy
    if _default_policy is None:
        # Default to project root (3 levels up from routing module)
        # src/agdd/routing/ -> src/agdd/ -> src/ -> root
        base_path = Path(__file__).resolve().parents[3]
        default_yaml = base_path / "catalog" / "routing" / "default.yaml"

        if default_yaml.exists():
            _default_policy = RoutingPolicy.from_yaml(default_yaml)
        else:
            # Fallback: create empty policy
            _default_policy = RoutingPolicy(
                name="default",
                description="Default routing policy (empty)",
                routes=[],
            )
    return _default_policy


def get_plan(
    task_type: str,
    overrides: Optional[dict[str, Any]] = None,
    policy: Optional[RoutingPolicy] = None,
) -> Optional[Plan]:
    """
    Get execution plan for task type.

    Args:
        task_type: Task type identifier (e.g., "offer-orchestration")
        overrides: Optional overrides for plan attributes
        policy: Optional routing policy (uses default if None)

    Returns:
        Plan instance or None if no matching route found

    Examples:
        >>> plan = get_plan("offer-orchestration")
        >>> if plan:
        ...     print(f"Provider: {plan.provider}, Model: {plan.model}")

        >>> plan = get_plan("offer-orchestration", overrides={"use_batch": True})
    """
    if policy is None:
        policy = _get_default_policy()

    route = policy.get_route(task_type, overrides=overrides)
    if route is None:
        return None

    return Plan.from_route(route)


def load_policy(policy_name: str, base_path: Optional[Path] = None) -> RoutingPolicy:
    """
    Load routing policy by name.

    Args:
        policy_name: Policy name (e.g., "default", "cost-optimized", "auto-optimize")
        base_path: Optional base path (defaults to project root)

    Returns:
        RoutingPolicy instance

    Raises:
        FileNotFoundError: If policy YAML not found
        ValueError: If YAML structure is invalid

    Examples:
        >>> policy = load_policy("cost-optimized")
        >>> plan = get_plan("offer-orchestration", policy=policy)
    """
    if base_path is None:
        base_path = Path(__file__).resolve().parents[3]

    policy_yaml = base_path / "catalog" / "routing" / f"{policy_name}.yaml"
    return RoutingPolicy.from_yaml(policy_yaml)
