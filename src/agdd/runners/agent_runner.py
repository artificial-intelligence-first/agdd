"""
Agent Runner - Orchestrates MAG and SAG execution with observability.

Provides invoke_mag() and invoke_sag() interfaces for agent invocation,
dependency resolution, and metrics collection.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, cast

import yaml

from agdd.observability.logger import ObservabilityLogger
from agdd.registry import AgentDescriptor, Registry, get_registry
from agdd.router import ExecutionPlan, Router, get_router
from agdd.routing.router import Plan as LLMPlan, get_plan as get_llm_plan

logger = logging.getLogger(__name__)

# Milliseconds per second for duration calculations
MS_PER_SECOND = 1000

AgentCallable = Callable[..., Dict[str, Any]]
SkillCallable = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass
class Delegation:
    """Request to delegate work to a sub-agent."""

    task_id: str
    sag_id: str  # Sub-agent slug
    input: Dict[str, Any]
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    """Result from agent execution."""

    task_id: str
    status: str  # "success", "failure", "partial"
    output: Dict[str, Any]
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class _ExecutionContext:
    """Container with execution artefacts shared across MAG/SAG invocations."""

    agent: AgentDescriptor
    execution_plan: ExecutionPlan
    plan_snapshot: dict[str, Any]
    llm_plan: LLMPlan
    observer: ObservabilityLogger


class SkillRuntime:
    """Skill execution runtime - delegates to skill implementations"""

    def __init__(self, registry: Optional[Registry] = None):
        self.registry = registry or get_registry()

    def exists(self, skill_id: str) -> bool:
        """Check if skill exists in registry"""
        try:
            self.registry.load_skill(skill_id)
            return True
        except (FileNotFoundError, ValueError):
            return False

    def invoke(self, skill_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a skill and return result"""
        skill_desc = self.registry.load_skill(skill_id)
        callable_fn = cast(SkillCallable, self.registry.resolve_entrypoint(skill_desc.entrypoint))
        return callable_fn(payload)


class AgentRunner:
    """Runner for MAG and SAG agents with execution planning and cost tracking"""

    def __init__(
        self,
        registry: Optional[Registry] = None,
        base_dir: Optional[Path] = None,
        router: Optional[Router] = None,
    ):
        self.registry: Registry = registry or get_registry()
        self.base_dir = base_dir
        self.skills = SkillRuntime(registry=self.registry)
        self.router: Router = router or get_router()
        self._task_index: dict[str, list[str]] | None = None

    def _load_task_index(self) -> dict[str, list[str]]:
        if self._task_index is None:
            self._task_index = self._build_task_index()
        return self._task_index

    def _build_task_index(self) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        registry_path = self.registry.base_path / "catalog" / "registry" / "agents.yaml"
        if not registry_path.exists():
            return index

        with open(registry_path, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}

        tasks = raw.get("tasks", [])
        if not isinstance(tasks, list):
            return index

        for task in tasks:
            if not isinstance(task, Mapping):
                continue
            target_slugs: list[str] = []
            for ref_key in ("default", "main_agent"):
                slug = Registry._normalize_agent_ref(task.get(ref_key))
                if slug:
                    target_slugs.append(slug)
            if not target_slugs:
                continue

            task_id = task.get("id")
            if not isinstance(task_id, str) or not task_id:
                continue

            for slug in target_slugs:
                bucket = index.setdefault(slug, [])
                if task_id not in bucket:
                    bucket.append(task_id)

        return index

    def _serialize_execution_plan(self, plan: ExecutionPlan) -> dict[str, Any]:
        return {
            "agent_slug": plan.agent_slug,
            "task_type": plan.task_type,
            "provider_hint": plan.provider_hint,
            "resource_tier": plan.resource_tier,
            "estimated_duration": plan.estimated_duration,
            "timeout_ms": plan.timeout_ms,
            "token_budget": plan.token_budget,
            "time_budget_s": plan.time_budget_s,
            "enable_otel": plan.enable_otel,
            "span_context": dict(plan.span_context),
            "metadata": dict(plan.metadata),
        }

    def _determine_task_type(self, agent: AgentDescriptor, context: Dict[str, Any]) -> str:
        task_type = context.get("task_type")
        if isinstance(task_type, str) and task_type:
            return task_type

        task_index = self._load_task_index()
        candidate_tasks = task_index.get(agent.slug)
        if candidate_tasks:
            return candidate_tasks[0]

        provider_config = agent.raw.get("provider_config", {})
        if isinstance(provider_config, Mapping):
            cfg_task = provider_config.get("task_type")
            if isinstance(cfg_task, str) and cfg_task:
                return cfg_task

        return agent.slug

    def _extract_llm_overrides(
        self,
        agent: AgentDescriptor,
        context: Dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        overrides: dict[str, Any] = {}
        candidate_sources: list[Any] = []

        context_override = context.get("llm_overrides") or context.get("plan_overrides")
        if context_override:
            candidate_sources.append(context_override)

        provider_config = agent.raw.get("provider_config", {})
        if isinstance(provider_config, Mapping):
            config_override = provider_config.get("llm_overrides")
            if config_override:
                candidate_sources.append(config_override)

        allowed_keys = {
            "provider",
            "model",
            "use_batch",
            "use_cache",
            "structured_output",
            "moderation",
            "metadata",
        }

        for source in candidate_sources:
            if not isinstance(source, Mapping):
                continue
            for key, value in source.items():
                if key in allowed_keys:
                    overrides[key] = value

        return overrides or None

    def _build_default_llm_plan(
        self,
        task_type: str,
        agent: AgentDescriptor,
        agent_plan_snapshot: dict[str, Any],
    ) -> LLMPlan:
        provider_config = agent.raw.get("provider_config", {})
        provider_hint: Optional[str] = None
        default_model: Optional[str] = None

        if isinstance(provider_config, Mapping):
            provider_hint = provider_config.get("provider_hint")
            default_model = provider_config.get("model")

        provider_name = provider_hint or agent_plan_snapshot.get("provider_hint") or "local"
        metadata = dict(agent_plan_snapshot.get("metadata", {}))
        metadata.setdefault("source", "fallback")
        model_name = metadata.get("model") or default_model or "unknown"

        return LLMPlan(
            task_type=task_type,
            provider=str(provider_name),
            model=str(model_name),
            use_batch=False,
            use_cache=False,
            structured_output=False,
            moderation=False,
            metadata=metadata,
        )

    def _resolve_llm_plan(
        self,
        agent: AgentDescriptor,
        context: Dict[str, Any],
        agent_plan_snapshot: dict[str, Any],
    ) -> LLMPlan:
        task_type = self._determine_task_type(agent, context)
        overrides = self._extract_llm_overrides(agent, context)
        plan = get_llm_plan(task_type, overrides=overrides)
        if plan is None:
            logger.debug("No routing plan found for task '%s'; using fallback.", task_type)
            return self._build_default_llm_plan(task_type, agent, agent_plan_snapshot)
        return plan

    def _plan_summary(self, execution_plan: ExecutionPlan, llm_plan: LLMPlan) -> dict[str, Any]:
        """Summarize execution and LLM plan details for logging."""
        return {
            "task_type": execution_plan.task_type,
            "provider_hint": execution_plan.provider_hint,
            "timeout_ms": execution_plan.timeout_ms,
            "token_budget": execution_plan.token_budget,
            "use_batch": llm_plan.use_batch,
            "use_cache": llm_plan.use_cache,
            "structured_output": llm_plan.structured_output,
            "moderation": llm_plan.moderation,
        }

    def _prepare_execution(
        self,
        slug: str,
        run_id: str,
        context: Optional[Dict[str, Any]],
    ) -> _ExecutionContext:
        """Load agent, compute plans, and create an observability logger."""
        effective_context: Dict[str, Any] = context or {}

        agent = self.registry.load_agent(slug)
        execution_plan = self.router.get_plan(agent, effective_context)
        plan_snapshot = self._serialize_execution_plan(execution_plan)
        llm_plan = self._resolve_llm_plan(agent, effective_context, plan_snapshot)

        parent_span_id = effective_context.get("parent_span_id") or execution_plan.span_context.get(
            "parent_span_id"
        )

        observer = ObservabilityLogger(
            run_id,
            slug=slug,
            base_dir=self.base_dir,
            agent_plan=plan_snapshot,
            llm_plan=llm_plan,
            enable_otel=execution_plan.enable_otel,
            parent_span_id=parent_span_id,
        )

        return _ExecutionContext(
            agent=agent,
            execution_plan=execution_plan,
            plan_snapshot=plan_snapshot,
            llm_plan=llm_plan,
            observer=observer,
        )

    def _record_placeholder_cost(
        self,
        ctx: _ExecutionContext,
        *,
        step: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record placeholder cost entries for observability consistency."""
        ctx.observer.record_cost(
            0.0,
            0,
            model=ctx.llm_plan.model if ctx.llm_plan else None,
            provider=ctx.llm_plan.provider if ctx.llm_plan else None,
            metadata=metadata,
            step=step,
        )

    def invoke_mag(
        self,
        slug: str,
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Invoke a Main Agent (MAG) with execution planning and cost tracking.

        Args:
            slug: Agent slug (e.g., "offer-orchestrator-mag")
            payload: Input data conforming to agent's input schema
            context: Optional context for distributed tracing and run_id retrieval.
                     If provided, the generated run_id will be written to context["run_id"].

        Returns:
            Output data conforming to agent's output schema

        Raises:
            Exception: If execution fails
        """
        context = context or {}
        run_id = f"mag-{uuid.uuid4().hex[:8]}"

        # Write run_id to context for caller retrieval
        context["run_id"] = run_id

        exec_ctx: Optional[_ExecutionContext] = None

        try:
            exec_ctx = self._prepare_execution(slug, run_id, context)
            obs = exec_ctx.observer

            obs.log(
                "start",
                {
                    "agent": exec_ctx.agent.name,
                    "slug": slug,
                    "plan": self._plan_summary(exec_ctx.execution_plan, exec_ctx.llm_plan),
                    "llm_plan": obs.llm_plan_snapshot,
                },
            )

            # Resolve entrypoint
            run_fn = cast(AgentCallable, self.registry.resolve_entrypoint(exec_ctx.agent.entrypoint))

            # Execute with dependencies injected
            t0 = time.time()
            output: Dict[str, Any] = run_fn(
                payload,
                registry=self.registry,
                skills=self.skills,
                runner=self,  # Allow MAG to delegate to SAG
                obs=obs,
            )
            duration_ms = int((time.time() - t0) * MS_PER_SECOND)

            # Record metrics and cost (placeholder - actual cost from LLM provider)
            obs.metric("duration_ms", duration_ms)
            self._record_placeholder_cost(exec_ctx, step="mag", metadata={"stage": "mag"})

            obs.log(
                "end",
                {
                    "status": "success",
                    "duration_ms": duration_ms,
                    "cost_usd": obs.cost_usd,
                    "tokens": obs.token_count,
                    "llm_plan": obs.llm_plan_snapshot,
                },
            )
            obs.finalize()

            return output

        except Exception as e:
            if exec_ctx is not None:
                exec_ctx.observer.log("error", {"error": str(e), "type": type(e).__name__})
                self._record_placeholder_cost(
                    exec_ctx,
                    step="mag",
                    metadata={"stage": "mag", "status": "exception"},
                )
                exec_ctx.observer.finalize()
            raise

    def invoke_sag(self, delegation: Delegation) -> Result:
        """
        Invoke a Sub-Agent (SAG) with execution planning and cost tracking.

        Args:
            delegation: Delegation request with task_id, sag_id, input, context

        Returns:
            Result with status, output, metrics

        Raises:
            Exception: If execution fails (with retry logic applied)
        """
        run_id = f"sag-{uuid.uuid4().hex[:8]}"

        exec_ctx: Optional[_ExecutionContext] = None
        context = delegation.context or {}

        try:
            exec_ctx = self._prepare_execution(delegation.sag_id, run_id, context)
            obs = exec_ctx.observer

            obs.log(
                "start",
                {
                    "agent": exec_ctx.agent.name,
                    "slug": delegation.sag_id,
                    "task_id": delegation.task_id,
                    "parent_run_id": context.get("parent_run_id"),
                    "plan": self._plan_summary(exec_ctx.execution_plan, exec_ctx.llm_plan),
                    "llm_plan": obs.llm_plan_snapshot,
                },
            )

            # Retry policy
            retry_policy = exec_ctx.agent.evaluation.get("retry_policy", {})
            max_attempts = retry_policy.get("max_attempts", 1)
            backoff_ms = retry_policy.get("backoff_ms", 0)

            last_error = None
            for attempt in range(max_attempts):
                try:
                    # Resolve entrypoint
                    run_fn = cast(
                        AgentCallable, self.registry.resolve_entrypoint(exec_ctx.agent.entrypoint)
                    )

                    # Execute
                    t0 = time.time()
                    output: Dict[str, Any] = run_fn(delegation.input, skills=self.skills, obs=obs)
                    duration_ms = int((time.time() - t0) * MS_PER_SECOND)

                    # Record metrics and cost
                    obs.metric("duration_ms", duration_ms)
                    self._record_placeholder_cost(
                        exec_ctx,
                        step=delegation.task_id,
                        metadata={"stage": "sag", "attempt": attempt + 1},
                    )

                    plan_snapshot = obs.llm_plan_snapshot
                    metrics: Dict[str, Any] = {
                        "duration_ms": duration_ms,
                        "attempts": attempt + 1,
                        "cost_usd": obs.cost_usd,
                        "tokens": obs.token_count,
                    }
                    if plan_snapshot:
                        metrics.update(
                            {
                                "provider": plan_snapshot.get("provider"),
                                "model": plan_snapshot.get("model"),
                                "use_batch": plan_snapshot.get("use_batch"),
                                "use_cache": plan_snapshot.get("use_cache"),
                                "structured_output": plan_snapshot.get("structured_output"),
                                "moderation": plan_snapshot.get("moderation"),
                                "llm_plan": plan_snapshot,
                            }
                        )

                    obs.log(
                        "end",
                        {
                            "status": "success",
                            "attempt": attempt + 1,
                            "duration_ms": duration_ms,
                            "cost_usd": obs.cost_usd,
                            "tokens": obs.token_count,
                            "llm_plan": plan_snapshot,
                        },
                    )
                    obs.finalize()

                    return Result(
                        task_id=delegation.task_id,
                        status="success",
                        output=output,
                        metrics=metrics,
                    )

                except Exception as e:
                    last_error = e
                    obs.log(
                        "retry",
                        {"attempt": attempt + 1, "error": str(e), "type": type(e).__name__},
                    )
                    if attempt < max_attempts - 1 and backoff_ms > 0:
                        time.sleep(backoff_ms / MS_PER_SECOND)

            # All attempts failed
            self._record_placeholder_cost(
                exec_ctx,
                step=delegation.task_id,
                metadata={"stage": "sag", "attempts": max_attempts, "status": "failure"},
            )
            plan_snapshot = obs.llm_plan_snapshot
            failure_metrics: Dict[str, Any] = {
                "attempts": max_attempts,
                "cost_usd": obs.cost_usd,
                "tokens": obs.token_count,
            }
            if plan_snapshot:
                failure_metrics.update(
                    {
                        "provider": plan_snapshot.get("provider"),
                        "model": plan_snapshot.get("model"),
                        "use_batch": plan_snapshot.get("use_batch"),
                        "use_cache": plan_snapshot.get("use_cache"),
                        "structured_output": plan_snapshot.get("structured_output"),
                        "moderation": plan_snapshot.get("moderation"),
                        "llm_plan": plan_snapshot,
                    }
                )

            obs.log(
                "error",
                {
                    "error": str(last_error),
                    "attempts": max_attempts,
                    "llm_plan": plan_snapshot,
                },
            )
            obs.finalize()

            return Result(
                task_id=delegation.task_id,
                status="failure",
                output={},
                metrics=failure_metrics,
                error=str(last_error),
            )

        except Exception as e:
            if exec_ctx is not None:
                self._record_placeholder_cost(
                    exec_ctx,
                    step=delegation.task_id,
                    metadata={"stage": "sag", "status": "exception"},
                )
                exec_ctx.observer.log("error", {"error": str(e), "type": type(e).__name__})
                exec_ctx.observer.finalize()
            raise


# Singleton instance
_runner: Optional[AgentRunner] = None


def get_runner(base_dir: Optional[Path] = None) -> AgentRunner:
    """Get or create the global runner instance"""
    global _runner
    if _runner is None or base_dir is not None:
        _runner = AgentRunner(base_dir=base_dir)
    return _runner


def invoke_mag(
    slug: str,
    payload: Dict[str, Any],
    base_dir: Optional[Path] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to invoke a MAG.

    Args:
        slug: Agent slug identifier
        payload: Input data conforming to agent's input schema
        base_dir: Optional base directory for run artifacts
        context: Optional context for distributed tracing and run_id retrieval.
                 If provided, the generated run_id will be written to context["run_id"].

    Returns:
        Output data conforming to agent's output schema
    """
    runner = get_runner(base_dir=base_dir)
    return runner.invoke_mag(slug, payload, context=context)


def invoke_sag(delegation: Delegation, base_dir: Optional[Path] = None) -> Result:
    """Convenience function to invoke a SAG"""
    runner = get_runner(base_dir=base_dir)
    return runner.invoke_sag(delegation)


__all__ = [
    "ObservabilityLogger",
    "Delegation",
    "Result",
    "SkillRuntime",
    "AgentRunner",
    "get_runner",
    "invoke_mag",
    "invoke_sag",
]
