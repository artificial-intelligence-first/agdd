"""
OfferOrchestratorMAG - Main agent for offer packet orchestration

Coordinates the generation of complete offer packets by:
1. Decomposing the request into tasks
2. Delegating to specialized sub-agents
3. Aggregating results into final offer packet
4. Managing state, context, and error handling
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class Delegation:
    """Request to delegate work to a sub-agent"""

    task_id: str
    sag_id: str
    input: Dict[str, Any]
    context: Dict[str, Any]


@dataclass
class Result:
    """Result from sub-agent execution"""

    task_id: str
    status: str
    output: Dict[str, Any]
    metrics: Dict[str, Any]
    error: Optional[str] = None


def _now_ms() -> int:
    """Get current timestamp in milliseconds"""
    return int(time.time() * 1000)


def run(payload: Dict[str, Any], *, registry=None, skills=None, runner=None, obs=None) -> Dict[str, Any]:
    """
    Orchestrate offer packet generation.

    Args:
        payload: Candidate profile conforming to candidate_profile schema
        registry: Agent/skill resolution interface (agdd.registry)
        skills: Skill execution runtime (agdd.skills.runtime)
        runner: Sub-agent invocation interface (agdd.runners.agent_runner)
        obs: Observability interface (logging/metrics)

    Returns:
        Offer packet conforming to offer_packet schema
    """
    # Use runner-provided run_id from ObservabilityLogger for consistency
    run_id = obs.run_id if obs else f"mag-{uuid.uuid4().hex[:8]}"
    t0 = _now_ms()

    if obs:
        obs.log(run_id, "start", {"agent": "OfferOrchestratorMAG"})

    try:
        # ===== Phase 1: Task Decomposition =====
        tasks = []
        if skills and skills.exists("skill.task-decomposition"):
            try:
                # Use task decomposition skill
                tasks = skills.invoke("skill.task-decomposition", {"candidate_profile": payload})
                if obs:
                    obs.log(run_id, "decomposition", {"task_count": len(tasks), "tasks": tasks})
            except Exception as e:
                if obs:
                    obs.log(run_id, "decomposition_error", {"error": str(e)})
                # Fallback to default single task
                tasks = [{"sag_id": "compensation-advisor-sag", "input": {"candidate_profile": payload}}]
        else:
            # Fallback: single task to compensation advisor
            tasks = [{"sag_id": "compensation-advisor-sag", "input": {"candidate_profile": payload}}]

        # ===== Phase 2: Sub-Agent Delegation =====
        results = []
        for idx, task in enumerate(tasks):
            task_id = f"task-{uuid.uuid4().hex[:6]}"

            delegation = Delegation(
                task_id=task_id,
                sag_id=task.get("sag_id", "compensation-advisor-sag"),
                input=task.get("input", {}),
                context={
                    "parent_run_id": run_id,
                    "task_index": idx,
                    "total_tasks": len(tasks),
                },
            )

            if obs:
                obs.log(
                    run_id,
                    "delegation_start",
                    {"task_id": task_id, "sag_id": delegation.sag_id, "index": idx},
                )

            try:
                # Invoke SAG via runner
                result = runner.invoke_sag(delegation)
                results.append(result)

                if obs:
                    obs.log(
                        run_id,
                        "delegation_complete",
                        {
                            "task_id": task_id,
                            "status": result.status,
                            "metrics": result.metrics,
                        },
                    )

                # Check for failures
                if result.status != "success":
                    if obs:
                        obs.log(
                            run_id,
                            "delegation_failure",
                            {"task_id": task_id, "error": result.error},
                        )
                    # Continue with partial results or raise based on policy
                    # For now, we'll continue and aggregate what we have

            except Exception as e:
                if obs:
                    obs.log(run_id, "delegation_error", {"task_id": task_id, "error": str(e)})
                # Create failure result
                results.append(
                    Result(
                        task_id=task_id,
                        status="failure",
                        output={},
                        metrics={},
                        error=str(e),
                    )
                )

        # ===== Phase 3: Result Aggregation =====
        output = {}
        if skills and skills.exists("skill.result-aggregation"):
            try:
                # Collect successful outputs
                successful_outputs = [r.output for r in results if r.status == "success"]
                aggregated = skills.invoke(
                    "skill.result-aggregation", {"results": successful_outputs}
                )
                output = aggregated
                if obs:
                    obs.log(run_id, "aggregation", {"result_count": len(successful_outputs)})
            except Exception as e:
                if obs:
                    obs.log(run_id, "aggregation_error", {"error": str(e)})
                # Fallback: use first successful result
                for result in results:
                    if result.status == "success":
                        output = result.output
                        break
        else:
            # Fallback: use first successful result
            for result in results:
                if result.status == "success":
                    output = result.output
                    break

        # ===== Phase 4: Enrich with Metadata =====
        final_output = {
            "offer": output.get("offer", {}),
            "metadata": {
                "generated_by": "OfferOrchestratorMAG",
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": "0.1.0",
                "task_count": len(tasks),
                "successful_tasks": sum(1 for r in results if r.status == "success"),
            },
        }

        # ===== Phase 5: Observability & Completion =====
        duration_ms = _now_ms() - t0
        if obs:
            obs.metric(run_id, "latency_ms", duration_ms)
            obs.metric(run_id, "task_count", len(tasks))
            obs.metric(run_id, "success_count", final_output["metadata"]["successful_tasks"])
            obs.log(
                run_id,
                "end",
                {
                    "status": "success",
                    "duration_ms": duration_ms,
                    "tasks": len(tasks),
                    "successful": final_output["metadata"]["successful_tasks"],
                },
            )

        return final_output

    except Exception as e:
        # Top-level error handling
        duration_ms = _now_ms() - t0
        if obs:
            obs.log(run_id, "error", {"error": str(e), "type": type(e).__name__, "duration_ms": duration_ms})
            obs.metric(run_id, "latency_ms", duration_ms)
        raise
