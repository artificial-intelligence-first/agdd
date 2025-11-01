"""Router for generating execution plans from routing policies."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Optional

from magsag.routing.policy import Route, RoutingPolicy


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
    """Get or load default routing policy from package resources."""
    global _default_policy
    if _default_policy is None:
        try:
            # Load from package resources (works in both dev and installed environments)
            resource = files("magsag.assets.routing").joinpath("default.yaml")
            if hasattr(resource, "read_text"):
                # Python 3.9+ Traversable API
                yaml_content = resource.read_text(encoding="utf-8")
                # Create a temporary file for RoutingPolicy.from_yaml
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".yaml", delete=False, encoding="utf-8"
                ) as tmp:
                    tmp.write(yaml_content)
                    tmp_path = Path(tmp.name)
                try:
                    _default_policy = RoutingPolicy.from_yaml(tmp_path)
                finally:
                    tmp_path.unlink()
            else:
                raise FileNotFoundError("default.yaml not found in package resources")
        except (FileNotFoundError, ModuleNotFoundError):
            # Fallback: create empty policy if resources not available
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
    Get execution plan for task type with unified provider selection support.

    Args:
        task_type: Task type identifier (e.g., "offer-orchestration")
        overrides: Optional overrides for plan attributes
        policy: Optional routing policy (uses default if None)

    Returns:
        Plan instance or None if no matching route found

    Environment Variables:
        MAGSAG_PROVIDER: Override provider for all tasks (e.g., "openai", "anthropic", "google", "local")
        MAGSAG_MODEL: Override model for all tasks (optional, provider-specific)

    Examples:
        >>> plan = get_plan("offer-orchestration")
        >>> if plan:
        ...     print(f"Provider: {plan.provider}, Model: {plan.model}")

        >>> plan = get_plan("offer-orchestration", overrides={"use_batch": True})

        >>> # Use environment variable to switch provider globally
        >>> os.environ["MAGSAG_PROVIDER"] = "openai"
        >>> plan = get_plan("offer-orchestration")  # Uses OpenAI regardless of policy
    """
    if policy is None:
        policy = _get_default_policy()

    # Apply environment variable overrides if set
    env_overrides = {}
    provider_env = os.getenv("MAGSAG_PROVIDER")
    if provider_env:
        env_overrides["provider"] = provider_env

    model_env = os.getenv("MAGSAG_MODEL")
    if model_env:
        env_overrides["model"] = model_env

    # Merge environment overrides with explicit overrides (explicit takes precedence)
    merged_overrides = {**env_overrides, **(overrides or {})}

    route = policy.get_route(task_type, overrides=merged_overrides if merged_overrides else None)
    if route is None:
        return None

    return Plan.from_route(route)


def load_policy(policy_name: str, base_path: Optional[Path] = None) -> RoutingPolicy:
    """
    Load routing policy by name from package resources or custom path.

    Args:
        policy_name: Policy name (e.g., "default", "cost-optimized", "auto-optimize")
        base_path: Optional base path for custom policies. If None, loads from package resources.

    Returns:
        RoutingPolicy instance

    Raises:
        FileNotFoundError: If policy YAML not found
        ValueError: If YAML structure is invalid

    Examples:
        >>> policy = load_policy("cost-optimized")
        >>> plan = get_plan("offer-orchestration", policy=policy)

        >>> # Load custom policy
        >>> custom_policy = load_policy("my-policy", base_path=Path("/custom/path"))
    """
    if base_path is not None:
        # Load from custom path
        policy_yaml = base_path / f"{policy_name}.yaml"
        return RoutingPolicy.from_yaml(policy_yaml)

    # Load from package resources
    try:
        resource = files("magsag.assets.routing").joinpath(f"{policy_name}.yaml")
        if hasattr(resource, "read_text"):
            yaml_content = resource.read_text(encoding="utf-8")
            # Create a temporary file for RoutingPolicy.from_yaml
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(yaml_content)
                tmp_path = Path(tmp.name)
            try:
                return RoutingPolicy.from_yaml(tmp_path)
            finally:
                tmp_path.unlink()
        else:
            raise FileNotFoundError(f"Policy '{policy_name}.yaml' not found in package resources")
    except (FileNotFoundError, ModuleNotFoundError) as e:
        raise FileNotFoundError(
            f"Policy '{policy_name}' not found in package resources. "
            f"Available policies: default, cost-optimized, auto-optimize"
        ) from e
