"""
Agent Runner - Orchestrates MAG and SAG execution with observability.

Provides invoke_mag() and invoke_sag() interfaces for agent invocation,
dependency resolution, and metrics collection.
"""

from __future__ import annotations

import json
import os
import time
import uuid
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional, cast

from agdd.registry import Registry, get_registry
from agdd.router import Router, get_router

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

    def record_cost(self, cost_usd: float, tokens: int = 0) -> None:
        """Record execution cost and token usage"""
        self.cost_usd += cost_usd
        self.token_count += tokens
        self.metric("cost_usd", cost_usd)
        self.metric("tokens", tokens)

    def finalize(self) -> None:
        """Write final summary with OTel and cost tracking"""
        summary_file = self.run_dir / "summary.json"
        summary = {
            "run_id": self.run_id,
            "total_logs": len(self.logs),
            "metrics": self.metrics,
            "run_dir": str(self.run_dir),
            "span_id": self.span_id,
            "cost_usd": self.cost_usd,
            "token_count": self.token_count,
        }
        # Include slug if provided (for run tracking/identification)
        if self.slug:
            summary["slug"] = self.slug
        if self.parent_span_id:
            summary["parent_span_id"] = self.parent_span_id
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
            context: Optional context for distributed tracing

        Returns:
            Output data conforming to agent's output schema

        Raises:
            Exception: If execution fails
        """
        context = context or {}
        run_id = f"mag-{uuid.uuid4().hex[:8]}"

        # Initialize obs early so it's available in exception handler
        obs: ObservabilityLogger | None = None

        try:
            # Load agent descriptor
            agent = self.registry.load_agent(slug)

            # Get execution plan from Router
            plan = self.router.get_plan(agent, context)

            # Create observability logger with OTel support
            parent_span_id = plan.span_context.get("parent_span_id")
            obs = ObservabilityLogger(
                run_id,
                slug=slug,
                base_dir=self.base_dir,
                parent_span_id=parent_span_id,
            )

            obs.log(
                "start",
                {
                    "agent": agent.name,
                    "slug": slug,
                    "plan": {
                        "task_type": plan.task_type,
                        "provider_hint": plan.provider_hint,
                        "timeout_ms": plan.timeout_ms,
                        "token_budget": plan.token_budget,
                    },
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
            # Note: In real implementation, cost would come from LLM provider API
            # For now, we track structure without real costs
            obs.record_cost(0.0, 0)

            obs.log(
                "end",
                {
                    "status": "success",
                    "duration_ms": duration_ms,
                    "cost_usd": obs.cost_usd,
                    "tokens": obs.token_count,
                },
            )
            obs.finalize()

            return output

        except Exception as e:
            if obs is not None:
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

        try:
            # Load agent descriptor
            agent = self.registry.load_agent(delegation.sag_id)

            # Get execution plan from Router
            plan = self.router.get_plan(agent, delegation.context)

            # Create observability logger with OTel support
            parent_span_id = delegation.context.get("parent_span_id") or plan.span_context.get(
                "parent_span_id"
            )
            obs = ObservabilityLogger(
                run_id,
                slug=delegation.sag_id,
                base_dir=self.base_dir,
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
                        "task_type": plan.task_type,
                        "provider_hint": plan.provider_hint,
                        "timeout_ms": plan.timeout_ms,
                        "token_budget": plan.token_budget,
                    },
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
                    obs.record_cost(0.0, 0)  # Placeholder for actual cost tracking

                    obs.log(
                        "end",
                        {
                            "status": "success",
                            "attempt": attempt + 1,
                            "duration_ms": duration_ms,
                            "cost_usd": obs.cost_usd,
                            "tokens": obs.token_count,
                        },
                    )
                    obs.finalize()

                    return Result(
                        task_id=delegation.task_id,
                        status="success",
                        output=output,
                        metrics={
                            "duration_ms": duration_ms,
                            "attempts": attempt + 1,
                            "cost_usd": obs.cost_usd,
                            "tokens": obs.token_count,
                        },
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
            obs.log("error", {"error": str(last_error), "attempts": max_attempts})
            obs.finalize()

            return Result(
                task_id=delegation.task_id,
                status="failure",
                output={},
                metrics={"attempts": max_attempts, "cost_usd": obs.cost_usd},
                error=str(last_error),
            )

        except Exception as e:
            if obs is not None:
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
    """Convenience function to invoke a MAG"""
    runner = get_runner(base_dir=base_dir)
    return runner.invoke_mag(slug, payload, context=context)


def invoke_sag(delegation: Delegation, base_dir: Optional[Path] = None) -> Result:
    """Convenience function to invoke a SAG"""
    runner = get_runner(base_dir=base_dir)
    return runner.invoke_sag(delegation)
