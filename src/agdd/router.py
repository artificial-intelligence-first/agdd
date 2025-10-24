"""
Execution Router - Plans agent execution based on provider config and budgets.

Provides get_plan() method to determine optimal execution strategy,
resource allocation, and provider selection for agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from agdd.registry import AgentDescriptor


@dataclass
class ExecutionPlan:
    """Execution plan with provider configuration and resource allocation"""

    agent_slug: str
    task_type: str  # orchestration, computation, io_bound, etc.
    provider_hint: str  # Provider selection hint (e.g., "openai", "anthropic", "local")
    resource_tier: str  # standard, high_memory, high_cpu, etc.
    estimated_duration: str  # short, medium, long
    timeout_ms: int  # Execution timeout in milliseconds
    token_budget: int  # Maximum tokens allowed
    time_budget_s: int  # Maximum time in seconds
    enable_otel: bool  # Enable OpenTelemetry tracing
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

    def __init__(self, default_provider: str = "local"):
        self.default_provider = default_provider

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

        return ExecutionPlan(
            agent_slug=agent.slug,
            task_type=task_type,
            provider_hint=provider_hint,
            resource_tier=resource_hint,
            estimated_duration=estimated_duration,
            timeout_ms=timeout_ms,
            token_budget=token_budget,
            time_budget_s=time_budget_s,
            enable_otel=enable_otel,
            span_context=span_context,
            metadata=metadata,
        )


# Singleton instance
_router: Optional[Router] = None


def get_router(default_provider: str = "local") -> Router:
    """Get or create the global router instance"""
    global _router
    if _router is None:
        _router = Router(default_provider=default_provider)
    return _router
