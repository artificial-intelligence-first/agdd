"""
Agent Runner - Orchestrates MAG and SAG execution with observability.

Provides invoke_mag() and invoke_sag() interfaces for agent invocation,
dependency resolution, and metrics collection.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional, cast

from agdd.registry import Registry, get_registry

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
    """Simple logger for agent execution traces"""

    def __init__(self, run_id: str, slug: Optional[str] = None, base_dir: Optional[Path] = None):
        self.run_id = run_id
        self.slug = slug
        self.base_dir = base_dir or Path.cwd() / ".runs" / "agents"
        self.run_dir = self.base_dir / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.logs: list[dict[str, Any]] = []
        self.metrics: dict[str, list[dict[str, Any]]] = {}

    def log(self, event: str, data: Dict[str, Any]) -> None:
        """Log an event"""
        entry = {
            "run_id": self.run_id,
            "event": event,
            "timestamp": time.time(),
            "data": data,
        }
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
        with open(metrics_file, "w", encoding="utf-8") as f:
            json.dump(self.metrics, f, ensure_ascii=False, indent=2)

    def finalize(self) -> None:
        """Write final summary"""
        summary_file = self.run_dir / "summary.json"
        summary = {
            "run_id": self.run_id,
            "total_logs": len(self.logs),
            "metrics": self.metrics,
            "run_dir": str(self.run_dir),
        }
        # Include slug if provided (for run tracking/identification)
        if self.slug:
            summary["slug"] = self.slug
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)


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
    """Runner for MAG and SAG agents"""

    def __init__(self, registry: Optional[Registry] = None, base_dir: Optional[Path] = None):
        self.registry: Registry = registry or get_registry()
        self.base_dir = base_dir
        self.skills = SkillRuntime(registry=self.registry)

    def invoke_mag(self, slug: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invoke a Main Agent (MAG).

        Args:
            slug: Agent slug (e.g., "offer-orchestrator-mag")
            payload: Input data conforming to agent's input schema

        Returns:
            Output data conforming to agent's output schema

        Raises:
            Exception: If execution fails
        """
        run_id = f"mag-{uuid.uuid4().hex[:8]}"
        obs = ObservabilityLogger(run_id, slug=slug, base_dir=self.base_dir)

        try:
            # Load agent descriptor
            agent = self.registry.load_agent(slug)
            obs.log("start", {"agent": agent.name, "slug": slug})

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
            duration_ms = int((time.time() - t0) * 1000)

            obs.metric("duration_ms", duration_ms)
            obs.log("end", {"status": "success", "duration_ms": duration_ms})
            obs.finalize()

            return output

        except Exception as e:
            obs.log("error", {"error": str(e), "type": type(e).__name__})
            obs.finalize()
            raise

    def invoke_sag(self, delegation: Delegation) -> Result:
        """
        Invoke a Sub-Agent (SAG).

        Args:
            delegation: Delegation request with task_id, sag_id, input, context

        Returns:
            Result with status, output, metrics

        Raises:
            Exception: If execution fails (with retry logic applied)
        """
        run_id = f"sag-{uuid.uuid4().hex[:8]}"
        obs = ObservabilityLogger(run_id, slug=delegation.sag_id, base_dir=self.base_dir)

        try:
            # Load agent descriptor
            agent = self.registry.load_agent(delegation.sag_id)
            obs.log(
                "start",
                {
                    "agent": agent.name,
                    "slug": delegation.sag_id,
                    "task_id": delegation.task_id,
                    "parent_run_id": delegation.context.get("parent_run_id"),
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
                    duration_ms = int((time.time() - t0) * 1000)

                    obs.metric("duration_ms", duration_ms)
                    obs.log(
                        "end",
                        {"status": "success", "attempt": attempt + 1, "duration_ms": duration_ms},
                    )
                    obs.finalize()

                    return Result(
                        task_id=delegation.task_id,
                        status="success",
                        output=output,
                        metrics={"duration_ms": duration_ms, "attempts": attempt + 1},
                    )

                except Exception as e:
                    last_error = e
                    obs.log(
                        "retry",
                        {"attempt": attempt + 1, "error": str(e), "type": type(e).__name__},
                    )
                    if attempt < max_attempts - 1 and backoff_ms > 0:
                        time.sleep(backoff_ms / 1000.0)

            # All attempts failed
            obs.log("error", {"error": str(last_error), "attempts": max_attempts})
            obs.finalize()

            return Result(
                task_id=delegation.task_id,
                status="failure",
                output={},
                metrics={"attempts": max_attempts},
                error=str(last_error),
            )

        except Exception as e:
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


def invoke_mag(slug: str, payload: Dict[str, Any], base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Convenience function to invoke a MAG"""
    runner = get_runner(base_dir=base_dir)
    return runner.invoke_mag(slug, payload)


def invoke_sag(delegation: Delegation, base_dir: Optional[Path] = None) -> Result:
    """Convenience function to invoke a SAG"""
    runner = get_runner(base_dir=base_dir)
    return runner.invoke_sag(delegation)
