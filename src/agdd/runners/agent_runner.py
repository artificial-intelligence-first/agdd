"""
Agent Runner - Orchestrates MAG and SAG execution with observability.

Provides invoke_mag() and invoke_sag() interfaces for agent invocation,
dependency resolution, and metrics collection.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, cast

import yaml

from agdd.observability.cost_tracker import record_llm_cost
from agdd.observability.tracing import initialize_observability
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
    """Request to delegate work to a sub-agent"""

    task_id: str
    sag_id: str  # Sub-agent slug
    input: Dict[str, Any]
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    """Result from agent execution"""

    task_id: str
    status: str  # "success", "failure", "partial"
    output: Dict[str, Any]
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class ObservabilityLogger:
    """Simple logger for agent execution traces with OTel and cost tracking support"""

    def __init__(
        self,
        run_id: str,
        slug: Optional[str] = None,
        base_dir: Optional[Path] = None,
        span_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        *,
        agent_plan: Optional[dict[str, Any]] = None,
        llm_plan: Optional[LLMPlan] = None,
        enable_otel: bool = False,
    ):
        self.run_id = run_id
        self.slug = slug
        self.base_dir = base_dir or Path.cwd() / ".runs" / "agents"
        self.run_dir = self.base_dir / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.logs: list[dict[str, Any]] = []
        self.metrics: dict[str, list[dict[str, Any]]] = {}
        self.span_id = span_id or f"span-{uuid.uuid4().hex[:16]}"
        self.parent_span_id = parent_span_id
        self.cost_usd: float = 0.0
        self.token_count: int = 0
        self._cost_entries: int = 0
        self._agent_plan_snapshot = copy.deepcopy(agent_plan) if agent_plan else None
        self._llm_plan_snapshot = self._serialize_llm_plan(llm_plan)
        self.enable_otel = enable_otel

        if enable_otel:
            try:
                initialize_observability()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to initialize observability tracing: %s", exc)

    @staticmethod
    def _serialize_llm_plan(plan: Optional[LLMPlan]) -> Optional[dict[str, Any]]:
        if plan is None:
            return None
        return {
            "task_type": plan.task_type,
            "provider": plan.provider,
            "model": plan.model,
            "use_batch": plan.use_batch,
            "use_cache": plan.use_cache,
            "structured_output": plan.structured_output,
            "moderation": plan.moderation,
            "metadata": copy.deepcopy(plan.metadata),
        }

    @property
    def llm_plan_snapshot(self) -> Optional[dict[str, Any]]:
        return copy.deepcopy(self._llm_plan_snapshot) if self._llm_plan_snapshot else None

    @property
    def agent_plan_snapshot(self) -> Optional[dict[str, Any]]:
        return copy.deepcopy(self._agent_plan_snapshot) if self._agent_plan_snapshot else None

    def _atomic_write(self, path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as tmp:
            tmp.write(payload)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)

    def _write_json(self, path: Path, content: Any) -> None:
        payload = json.dumps(content, ensure_ascii=False, indent=2)
        self._atomic_write(path, payload + "\n")

    def log(self, event: str, data: Dict[str, Any]) -> None:
        """Log an event with OTel span context"""
        entry = {
            "run_id": self.run_id,
            "event": event,
            "timestamp": time.time(),
            "data": data,
            "span_id": self.span_id,
        }
        if self.parent_span_id:
            entry["parent_span_id"] = self.parent_span_id
        self.logs.append(entry)
        # Write immediately for observability
        log_file = self.run_dir / "logs.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def metric(self, key: str, value: Any) -> None:
        """Record a metric"""
        if key not in self.metrics:
            self.metrics[key] = []
        self.metrics[key].append({"run_id": self.run_id, "value": value, "timestamp": time.time()})
        # Write metrics
        metrics_file = self.run_dir / "metrics.json"
        self._write_json(metrics_file, self.metrics)

    def record_cost(
        self,
        cost_usd: float,
        tokens: int = 0,
        *,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        step: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record execution cost and token usage"""
        self.cost_usd += cost_usd
        self.token_count += tokens
        self.metric("cost_usd", cost_usd)
        self.metric("tokens", tokens)
        self._cost_entries += 1

        plan_snapshot = self.llm_plan_snapshot
        model_name = model or (plan_snapshot["model"] if plan_snapshot else "unknown")
        provider_name = provider or (plan_snapshot["provider"] if plan_snapshot else None)

        tracker_metadata: Dict[str, Any] = {
            "provider": provider_name,
            "agent_plan": self.agent_plan_snapshot,
            "llm_plan": plan_snapshot,
        }
        if metadata:
            tracker_metadata.update(metadata)

        placeholder = (
            cost_usd == 0.0
            and int(input_tokens if input_tokens is not None else tokens) == 0
            and int(output_tokens or 0) == 0
        )
        if placeholder:
            tracker_metadata.setdefault("placeholder", True)

        record_llm_cost(
            model=model_name,
            input_tokens=int(input_tokens if input_tokens is not None else tokens),
            output_tokens=int(output_tokens if output_tokens is not None else 0),
            cost_usd=cost_usd,
            run_id=self.run_id,
            step=step,
            agent=self.slug,
            metadata={k: v for k, v in tracker_metadata.items() if v is not None},
        )

    def finalize(self) -> None:
        """Write final summary with OTel and cost tracking"""
        if self._cost_entries == 0:
            # Ensure a placeholder entry exists for downstream cost analysis
            self.record_cost(0.0, 0, step="finalize", metadata={"auto_recorded": True})

        summary_file = self.run_dir / "summary.json"
        summary = {
            "run_id": self.run_id,
            "total_logs": len(self.logs),
            "metrics": self.metrics,
            "run_dir": str(self.run_dir),
            "span_id": self.span_id,
            "cost_usd": self.cost_usd,
            "token_count": self.token_count,
            "otel_enabled": self.enable_otel,
        }
        if self.slug:
            summary["slug"] = self.slug
        if self.parent_span_id:
            summary["parent_span_id"] = self.parent_span_id
        if self._agent_plan_snapshot:
            summary["agent_plan"] = self._agent_plan_snapshot
        if self._llm_plan_snapshot:
            summary["llm_plan"] = self._llm_plan_snapshot
        self._write_json(summary_file, summary)


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

        # Initialize obs early so it's available in exception handler
        obs: ObservabilityLogger | None = None

        agent_plan_snapshot: Optional[dict[str, Any]] = None
        llm_plan: Optional[LLMPlan] = None

        try:
            # Load agent descriptor
            agent = self.registry.load_agent(slug)

            # Get execution plan and derive LLM routing plan
            execution_plan = self.router.get_plan(agent, context)
            agent_plan_snapshot = self._serialize_execution_plan(execution_plan)
            llm_plan = self._resolve_llm_plan(agent, context, agent_plan_snapshot)

            # Create observability logger with OTel support
            parent_span_id = execution_plan.span_context.get("parent_span_id")
            obs = ObservabilityLogger(
                run_id,
                slug=slug,
                base_dir=self.base_dir,
                agent_plan=agent_plan_snapshot,
                llm_plan=llm_plan,
                enable_otel=execution_plan.enable_otel,
                parent_span_id=parent_span_id,
            )

            obs.log(
                "start",
                {
                    "agent": agent.name,
                    "slug": slug,
                    "plan": {
                        "task_type": execution_plan.task_type,
                        "provider_hint": execution_plan.provider_hint,
                        "timeout_ms": execution_plan.timeout_ms,
                        "token_budget": execution_plan.token_budget,
                        "use_batch": llm_plan.use_batch,
                        "use_cache": llm_plan.use_cache,
                        "structured_output": llm_plan.structured_output,
                        "moderation": llm_plan.moderation,
                    },
                    "llm_plan": obs.llm_plan_snapshot,
                },
            )

            # Resolve entrypoint
            run_fn = cast(AgentCallable, self.registry.resolve_entrypoint(agent.entrypoint))

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
            obs.record_cost(
                0.0,
                0,
                model=llm_plan.model if llm_plan else None,
                provider=llm_plan.provider if llm_plan else None,
                metadata={"stage": "mag"},
                step="mag",
            )

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
            if obs is not None:
                obs.record_cost(
                    0.0,
                    0,
                    model=llm_plan.model if llm_plan else None,
                    provider=llm_plan.provider if llm_plan else None,
                    metadata={"stage": "mag", "status": "exception"},
                    step="mag",
                )
                obs.log("error", {"error": str(e), "type": type(e).__name__})
                obs.finalize()
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

        # Initialize obs early so it's available in exception handler
        obs: ObservabilityLogger | None = None
        agent_plan_snapshot: Optional[dict[str, Any]] = None
        llm_plan: Optional[LLMPlan] = None

        try:
            # Load agent descriptor
            agent = self.registry.load_agent(delegation.sag_id)

            # Get execution plan and derive LLM routing plan
            execution_plan = self.router.get_plan(agent, delegation.context)
            agent_plan_snapshot = self._serialize_execution_plan(execution_plan)
            llm_plan = self._resolve_llm_plan(agent, delegation.context, agent_plan_snapshot)

            # Create observability logger with OTel support
            parent_span_id = delegation.context.get("parent_span_id") or execution_plan.span_context.get(
                "parent_span_id"
            )
            obs = ObservabilityLogger(
                run_id,
                slug=delegation.sag_id,
                base_dir=self.base_dir,
                agent_plan=agent_plan_snapshot,
                llm_plan=llm_plan,
                enable_otel=execution_plan.enable_otel,
                parent_span_id=parent_span_id,
            )

            obs.log(
                "start",
                {
                    "agent": agent.name,
                    "slug": delegation.sag_id,
                    "task_id": delegation.task_id,
                    "parent_run_id": delegation.context.get("parent_run_id"),
                    "plan": {
                        "task_type": execution_plan.task_type,
                        "provider_hint": execution_plan.provider_hint,
                        "timeout_ms": execution_plan.timeout_ms,
                        "token_budget": execution_plan.token_budget,
                        "use_batch": llm_plan.use_batch,
                        "use_cache": llm_plan.use_cache,
                        "structured_output": llm_plan.structured_output,
                        "moderation": llm_plan.moderation,
                    },
                    "llm_plan": obs.llm_plan_snapshot,
                },
            )

            # Retry policy
            retry_policy = agent.evaluation.get("retry_policy", {})
            max_attempts = retry_policy.get("max_attempts", 1)
            backoff_ms = retry_policy.get("backoff_ms", 0)

            last_error = None
            for attempt in range(max_attempts):
                try:
                    # Resolve entrypoint
                    run_fn = cast(AgentCallable, self.registry.resolve_entrypoint(agent.entrypoint))

                    # Execute
                    t0 = time.time()
                    output: Dict[str, Any] = run_fn(delegation.input, skills=self.skills, obs=obs)
                    duration_ms = int((time.time() - t0) * MS_PER_SECOND)

                    # Record metrics and cost
                    obs.metric("duration_ms", duration_ms)
                    obs.record_cost(
                        0.0,
                        0,
                        model=llm_plan.model if llm_plan else None,
                        provider=llm_plan.provider if llm_plan else None,
                        metadata={"stage": "sag", "attempt": attempt + 1},
                        step=delegation.task_id,
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
            obs.record_cost(
                0.0,
                0,
                model=llm_plan.model if llm_plan else None,
                provider=llm_plan.provider if llm_plan else None,
                metadata={"stage": "sag", "attempts": max_attempts, "status": "failure"},
                step=delegation.task_id,
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
            if obs is not None:
                obs.record_cost(
                    0.0,
                    0,
                    model=llm_plan.model if llm_plan else None,
                    provider=llm_plan.provider if llm_plan else None,
                    metadata={"stage": "sag", "status": "exception"},
                    step=delegation.task_id,
                )
                obs.log("error", {"error": str(e), "type": type(e).__name__})
                obs.finalize()
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
