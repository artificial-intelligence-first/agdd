"""Execution router that aligns agent plans with optimization policies.

This module bridges catalog agent descriptors with the cost optimizer so that
the resulting :class:`ExecutionPlan` exposes provider, caching, batching, and
moderation hints expected by downstream runners. The plan integrates
Service-Level Agreement (SLA) data and maps it to concrete execution
strategies such as batch mode and semantic cache usage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from agdd.optimization.optimizer import (
    CacheStrategy,
    CostOptimizer,
    ExecutionPlan as OptimizationPlan,
    SLAParameters,
)
from agdd.registry import AgentDescriptor

logger = logging.getLogger(__name__)


@dataclass
class ExecutionPlan:
    """Execution plan with provider configuration and execution strategy."""

    agent_slug: str
    task_type: str  # orchestration, computation, io_bound, etc.
    provider_hint: str  # Provider selection hint (e.g., "openai", "anthropic", "local")
    provider: str  # Resolved provider identifier
    model: Optional[str]  # Preferred model identifier if specified
    resource_tier: str  # standard, high_memory, high_cpu, etc.
    estimated_duration: str  # short, medium, long
    timeout_ms: int  # Execution timeout in milliseconds
    token_budget: int  # Maximum tokens allowed
    time_budget_s: int  # Maximum time in seconds
    enable_otel: bool  # Enable OpenTelemetry tracing
    use_batch: bool  # Whether batch execution is recommended
    use_cache: bool  # Whether semantic cache should be leveraged
    structured_output: bool  # Whether structured outputs are expected
    moderation: bool  # Whether moderation should wrap requests/responses
    cache_strategy: CacheStrategy  # Selected cache policy
    estimated_cost_usd: float  # Estimated cost from optimizer
    estimated_latency_ms: int  # Estimated latency from optimizer
    optimization: OptimizationPlan  # Raw optimization decision for auditing
    span_context: Dict[str, str] = field(default_factory=dict)  # OTel span context
    metadata: Dict[str, Any] = field(default_factory=dict)  # Additional metadata


class Router:
    """Router for planning agent execution strategy"""

    # Default timeout mappings (in milliseconds)
    DURATION_TO_TIMEOUT_MS = {
        "short": 30_000,  # 30s
        "medium": 120_000,  # 2min
        "long": 300_000,  # 5min
    }

    # Default resource tier configurations
    RESOURCE_TIERS = {
        "standard": {"cpu_hint": "1-2", "memory_hint": "2GB"},
        "high_memory": {"cpu_hint": "2-4", "memory_hint": "8GB"},
        "high_cpu": {"cpu_hint": "4-8", "memory_hint": "4GB"},
    }

    def __init__(
        self,
        default_provider: str = "local",
        optimizer: Optional[CostOptimizer] = None,
    ):
        self.default_provider = default_provider
        self.optimizer = optimizer or CostOptimizer()

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y", "on"}:
                return True
            if normalized in {"false", "0", "no", "n", "off"}:
                return False
        return default

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                return None
        return None

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_cache_strategy(value: Any, default: CacheStrategy) -> CacheStrategy:
        if isinstance(value, CacheStrategy):
            return value
        if isinstance(value, str):
            try:
                return CacheStrategy(value.strip().lower())
            except ValueError:
                logger.debug("Unknown cache strategy '%s'; using default '%s'.", value, default)
        return default

    def get_plan(
        self,
        agent: AgentDescriptor,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionPlan:
        """
        Generate execution plan for an agent.

        Args:
            agent: Agent descriptor with metadata
            context: Additional context (e.g., parent span_id, task metadata)

        Returns:
            ExecutionPlan with provider config and resource allocation
        """
        context = context or {}

        # Extract provider config from agent.yaml
        provider_config = agent.raw.get("provider_config", {})
        task_type = provider_config.get("task_type", "general")
        estimated_duration = provider_config.get("estimated_duration", "medium")
        resource_hint = provider_config.get("resource_hint", "standard")
        provider_hint = provider_config.get("provider_hint", self.default_provider)
        provider_name = str(provider_config.get("provider", provider_hint))
        model_preference = provider_config.get("model")
        if isinstance(model_preference, str):
            model_preference = model_preference.strip() or None
        else:
            model_preference = None

        allow_batch = self._coerce_bool(provider_config.get("allow_batch"), True)
        allow_cache = self._coerce_bool(provider_config.get("allow_cache"), True)
        use_batch_override = provider_config.get("use_batch")
        use_cache_override = provider_config.get("use_cache")
        structured_output_override = provider_config.get("structured_output")
        moderation_override = provider_config.get("moderation")
        cache_strategy_override = provider_config.get("cache_strategy")

        # Extract budgets
        budgets = agent.budgets or {}
        token_budget = budgets.get("tokens", 100_000)
        time_budget_s = budgets.get("time_s", 120)

        # Calculate timeout from estimated duration with fallback to time budget
        timeout_ms = self.DURATION_TO_TIMEOUT_MS.get(estimated_duration, time_budget_s * 1000)

        # Enable OTel if configured in agent observability settings
        observability = agent.observability or {}
        enable_otel = observability.get("traces") in ("basic", "detailed", True)

        # Build span context for distributed tracing
        span_context: Dict[str, str] = {}
        if enable_otel and context:
            if "parent_span_id" in context:
                span_context["parent_span_id"] = str(context["parent_span_id"])
            if "trace_id" in context:
                span_context["trace_id"] = str(context["trace_id"])

        # Build metadata
        metadata = {
            "agent_name": agent.name,
            "agent_version": agent.version,
            "role": agent.role,
            "risk_class": agent.risk_class,
        }

        # Determine SLA parameters for cost optimization
        sla_config = provider_config.get("sla", {})
        if not isinstance(sla_config, dict):
            sla_config = {}

        sla_params = SLAParameters(
            max_latency_ms=self._coerce_int(sla_config.get("max_latency_ms"))
            or (time_budget_s * 1000 if estimated_duration == "short" else None),
            max_cost_usd=self._coerce_float(sla_config.get("max_cost_usd")),
            min_quality=float(self._coerce_float(sla_config.get("min_quality")) or 0.7),
            realtime_required=self._coerce_bool(
                sla_config.get("realtime_required"), estimated_duration != "long"
            ),
            allow_cache=self._coerce_bool(sla_config.get("allow_cache"), allow_cache),
            allow_batch=self._coerce_bool(sla_config.get("allow_batch"), allow_batch),
        )

        optimization_plan = self.optimizer.optimize(sla_params)

        cache_strategy = optimization_plan.cache_strategy
        if not sla_params.allow_cache:
            cache_strategy = CacheStrategy.NONE

        cache_strategy = self._parse_cache_strategy(cache_strategy_override, cache_strategy)

        use_batch = optimization_plan.enable_batch and sla_params.allow_batch
        if isinstance(use_batch_override, bool):
            use_batch = use_batch_override
        use_cache = cache_strategy is not CacheStrategy.NONE
        if isinstance(use_cache_override, bool):
            use_cache = use_cache_override

        structured_output = bool(agent.contracts.get("output_schema"))
        if isinstance(structured_output_override, bool):
            structured_output = structured_output_override

        moderation_default = agent.risk_class.lower() not in {"low", "none"}
        moderation = self._coerce_bool(moderation_override, moderation_default)

        estimated_cost_usd = optimization_plan.estimated_cost_usd
        estimated_latency_ms = optimization_plan.estimated_latency_ms

        metadata.update(
            {
                "provider": provider_name,
                "model": model_preference,
                "cache_strategy": cache_strategy.value,
                "execution_mode": optimization_plan.mode.value,
                "model_tier": optimization_plan.model_tier.value,
                "estimated_cost_usd": estimated_cost_usd,
                "estimated_latency_ms": estimated_latency_ms,
                "use_batch": use_batch,
                "use_cache": use_cache,
                "structured_output": structured_output,
                "moderation": moderation,
            }
        )

        return ExecutionPlan(
            agent_slug=agent.slug,
            task_type=task_type,
            provider_hint=provider_hint,
            provider=provider_name,
            model=model_preference,
            resource_tier=resource_hint,
            estimated_duration=estimated_duration,
            timeout_ms=timeout_ms,
            token_budget=token_budget,
            time_budget_s=time_budget_s,
            enable_otel=enable_otel,
            use_batch=use_batch,
            use_cache=use_cache,
            structured_output=structured_output,
            moderation=moderation,
            cache_strategy=cache_strategy,
            estimated_cost_usd=estimated_cost_usd,
            estimated_latency_ms=estimated_latency_ms,
            optimization=optimization_plan,
            span_context=span_context,
            metadata=metadata,
        )


# Singleton instance
_router: Optional[Router] = None


def get_router(
    default_provider: str = "local",
    optimizer: Optional[CostOptimizer] = None,
) -> Router:
    """Get or create the global router instance"""
    global _router
    if _router is None:
        _router = Router(default_provider=default_provider, optimizer=optimizer)
    else:
        if optimizer is not None:
            _router.optimizer = optimizer
        _router.default_provider = default_provider
    return _router
