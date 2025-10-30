"""
OfferOrchestratorMAG - Main agent for offer packet orchestration

Coordinates the generation of complete offer packets by:
1. Decomposing the request into tasks
2. Delegating to specialized sub-agents
3. Aggregating results into final offer packet
4. Managing state, context, and error handling
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

# Import shared dataclasses from agent_runner
# Note: These will be injected via the runner parameter, but we need them for type hints
try:
    from agdd.runners.agent_runner import Delegation, Result
except ImportError:
    # Fallback for when running outside package context
    from dataclasses import dataclass
    from typing import Optional

    @dataclass
    class Delegation:
        task_id: str
        sag_id: str
        input: Dict[str, Any]
        context: Dict[str, Any]

    @dataclass
    class Result:
        task_id: str
        status: str
        output: Dict[str, Any]
        metrics: Dict[str, Any]
        error: Optional[str] = None


def _now_ms() -> int:
    """Get current timestamp in milliseconds"""
    return int(time.time() * 1000)


async def run(
    payload: Dict[str, Any], *, registry=None, skills=None, runner=None, obs=None
) -> Dict[str, Any]:
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

    Raises:
        RuntimeError: If all SAG delegations fail
    """
    t0 = _now_ms()

    if obs:
        obs.log("start", {"agent": "OfferOrchestratorMAG"})

    try:
        # ===== Phase 1: Task Decomposition =====
        tasks = []
        if skills and skills.exists("skill.task-decomposition"):
            try:
                # Use task decomposition skill
                tasks = await skills.invoke_async(
                    "skill.task-decomposition", {"candidate_profile": payload}
                )
                if obs:
                    obs.log("decomposition", {"task_count": len(tasks), "tasks": tasks})
            except Exception as e:
                if obs:
                    obs.log("decomposition_error", {"error": str(e)})
                # Fallback to default single task
                tasks = [
                    {"sag_id": "compensation-advisor-sag", "input": {"candidate_profile": payload}}
                ]
        else:
            # Fallback: single task to compensation advisor
            tasks = [
                {"sag_id": "compensation-advisor-sag", "input": {"candidate_profile": payload}}
            ]

        # ===== Phase 2: Sub-Agent Delegation =====
        results = []
        for idx, task in enumerate(tasks):
            task_id = f"task-{uuid.uuid4().hex[:6]}"

            delegation = Delegation(
                task_id=task_id,
                sag_id=task.get("sag_id", "compensation-advisor-sag"),
                input=task.get("input", {}),
                context={
                    "parent_run_id": obs.run_id if obs else "unknown",
                    "task_index": idx,
                    "total_tasks": len(tasks),
                },
            )

            if obs:
                obs.log(
                    "delegation_start",
                    {"task_id": task_id, "sag_id": delegation.sag_id, "index": idx},
                )

            try:
                # Invoke SAG via runner (async to avoid thread/event loop nesting)
                result = await runner.invoke_sag_async(delegation)
                results.append(result)

                if obs:
                    obs.log(
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
                            "delegation_failure",
                            {"task_id": task_id, "error": result.error},
                        )
                    # Continue with partial results or raise based on policy
                    # For now, we'll continue and aggregate what we have

            except Exception as e:
                if obs:
                    obs.log("delegation_error", {"task_id": task_id, "error": str(e)})
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
        successful_count = sum(1 for r in results if r.status == "success")

        # Check if all delegations failed
        if successful_count == 0:
            duration_ms = _now_ms() - t0
            if obs:
                obs.log(
                    "all_delegations_failed",
                    {
                        "total_tasks": len(tasks),
                        "failed_tasks": len(results),
                        "duration_ms": duration_ms,
                    },
                )
                obs.metric("latency_ms", duration_ms)
            raise RuntimeError(
                f"All {len(tasks)} SAG delegation(s) failed. Cannot generate valid offer packet."
            )

        if skills and skills.exists("skill.result-aggregation"):
            try:
                # Collect successful outputs
                successful_outputs = [r.output for r in results if r.status == "success"]
                aggregated = await skills.invoke_async(
                    "skill.result-aggregation", {"results": successful_outputs}
                )
                output = aggregated
                if obs:
                    obs.log("aggregation", {"result_count": len(successful_outputs)})
            except Exception as e:
                if obs:
                    obs.log("aggregation_error", {"error": str(e)})
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
                "run_id": obs.run_id if obs else f"mag-{uuid.uuid4().hex[:8]}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": "0.1.0",
                "task_count": len(tasks),
                "successful_tasks": successful_count,
            },
        }

        # ===== Phase 5: Observability & Completion =====
        duration_ms = _now_ms() - t0
        if obs:
            obs.metric("latency_ms", duration_ms)
            obs.metric("task_count", len(tasks))
            obs.metric("success_count", successful_count)
            obs.log(
                "end",
                {
                    "status": "success",
                    "duration_ms": duration_ms,
                    "tasks": len(tasks),
                    "successful": successful_count,
                },
            )

        return final_output

    except Exception as e:
        # Top-level error handling
        duration_ms = _now_ms() - t0
        if obs:
            obs.log(
                "error", {"error": str(e), "type": type(e).__name__, "duration_ms": duration_ms}
            )
            obs.metric("latency_ms", duration_ms)
        raise
