"""Planner facade that wraps Router and returns PlanIR."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    try:
        from magsag.core.types import PlanIR
    except ImportError:
        PlanIR = Any  # type: ignore
else:
    PlanIR = Any

from magsag.routing import RoutingPolicy
from magsag.routing.router import Plan, get_plan


class Planner:
    """
    Planner facade that wraps the existing Router functionality.

    This class provides a higher-level interface for generating execution plans,
    returning PlanIR objects that can be used by other components in the system.

    Attributes:
        _policy: Optional routing policy to use for plan generation
    """

    def __init__(self, policy: Optional[RoutingPolicy] = None):
        """
        Initialize Planner with optional routing policy.

        Args:
            policy: Optional routing policy to use. If None, uses default policy.
        """
        self._policy = policy

    def plan(
        self,
        task_type: str,
        overrides: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Optional[PlanIR]:
        """
        Generate execution plan for given task type.

        This method wraps the existing Router functionality and converts
        the result to PlanIR format for consumption by other components.

        Args:
            task_type: Task type identifier (e.g., "offer-orchestration")
            overrides: Optional overrides for plan attributes
            **kwargs: Additional keyword arguments for future extensibility

        Returns:
            PlanIR instance or None if no matching route found

        Examples:
            >>> planner = Planner()
            >>> plan_ir = planner.plan("offer-orchestration")
            >>> if plan_ir:
            ...     print(f"Generated plan for {plan_ir.task_type}")

            >>> # With overrides
            >>> plan_ir = planner.plan(
            ...     "offer-orchestration",
            ...     overrides={"use_batch": True}
            ... )
        """
        # Use existing router logic
        route_result = get_plan(
            task_type=task_type,
            overrides=overrides,
            policy=self._policy,
        )

        if route_result is None:
            return None

        # Convert to PlanIR format
        return self._convert_to_plan_ir(route_result)

    def _convert_to_plan_ir(self, plan: Plan) -> PlanIR:
        """
        Convert Router Plan to PlanIR format.

        This method ensures compatibility between the Router's Plan format
        and the PlanIR format expected by other components per PLANS.md spec.

        Args:
            plan: Plan instance from Router

        Returns:
            PlanIR instance with equivalent data

        Note:
            PlanIR structure per PLANS.md includes chain, sla_ms, cost_budget
            which are not present in router Plan. These are extracted from
            metadata or provided as reasonable defaults.
        """
        # Extract optional fields from metadata
        sla_ms = plan.metadata.get("sla_ms", 30000)  # Default 30s
        cost_budget = plan.metadata.get("cost_budget", None)

        # Create single-step chain from current plan
        # Chain represents ordered fallback steps; initially just one step
        chain = [
            {
                "provider": plan.provider,
                "model": plan.model,
                "use_batch": plan.use_batch,
                "use_cache": plan.use_cache,
                "structured_output": plan.structured_output,
                "moderation": plan.moderation,
            }
        ]

        # Construct PlanIR-compatible structure
        # When actual PlanIR type is available (WS-01), this will return that type
        plan_ir = {
            "chain": chain,
            "provider": plan.provider,
            "model": plan.model,
            "use_batch": plan.use_batch,
            "use_cache": plan.use_cache,
            "structured_output": plan.structured_output,
            "moderation": plan.moderation,
            "sla_ms": sla_ms,
            "cost_budget": cost_budget,
        }

        return plan_ir  # type: ignore
