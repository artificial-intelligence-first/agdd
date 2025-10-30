"""
YourA2AOrchestratorMAG - A2A-enabled Template for Main Agent orchestration

This template extends the standard MAG template with A2A (Agent-to-Agent) capabilities:
- Discovery: Agents can discover this orchestrator via API
- Invocation: Agents can invoke this orchestrator via API
- Tracing: Enhanced observability for A2A communication flows

Customize this template with your orchestration workflow before production use.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Import shared dataclasses from agent_runner
try:
    from agdd.runners.agent_runner import Delegation, Result  # type: ignore[import-not-found]
except ImportError:
    # Fallback for when running outside package context
    from dataclasses import dataclass

    @dataclass
    class Delegation:  # type: ignore[no-redef]
        task_id: str
        sag_id: str
        input: Dict[str, Any]
        context: Dict[str, Any]

    @dataclass
    class Result:  # type: ignore[no-redef]
        task_id: str
        status: str
        output: Dict[str, Any]
        metrics: Dict[str, Any]
        error: Optional[str] = None


def _now_ms() -> int:
    """Get current timestamp in milliseconds"""
    return int(time.time() * 1000)


async def run(
    payload: Dict[str, Any],
    *,
    registry: Any = None,
    skills: Any = None,
    runner: Any = None,
    obs: Any = None,
) -> Dict[str, Any]:
    """
    A2A-enabled orchestration logic.

    Args:
        payload: Input data conforming to a2a_orchestrator_input schema
        registry: Agent/skill resolution interface
        skills: Skill execution runtime
        runner: Sub-agent invocation interface
        obs: Observability interface (logging/metrics)

    Returns:
        Output conforming to a2a_orchestrator_output schema

    Raises:
        RuntimeError: If all SAG delegations fail
    """
    t0 = _now_ms()

    if obs:
        obs.log("start", {"agent": "YourA2AOrchestratorMAG", "a2a_enabled": True})

    try:
        # ===== Extract A2A Context =====
        # A2A requests may include additional context for tracing
        a2a_context = payload.get("context", {})
        correlation_id = a2a_context.get("correlation_id", str(uuid.uuid4()))
        source_agent = a2a_context.get("source_agent", "unknown")

        if obs:
            obs.log(
                "a2a_request_received",
                {
                    "correlation_id": correlation_id,
                    "source_agent": source_agent,
                    "request_type": payload.get("request_type", "unknown"),
                },
            )

        # Extract the actual data payload
        data = payload.get("data", payload)

        # ===== Phase 1: Task Decomposition =====
        tasks: List[Dict[str, Any]] = []
        if skills and skills.exists("skill.task-decomposition"):
            try:
                # Adjust the task decomposition payload to match your input contract.
                tasks = await skills.invoke_async("skill.task-decomposition", {"input": data})
                if obs:
                    obs.log("decomposition", {"task_count": len(tasks), "tasks": tasks})
            except Exception as e:
                if obs:
                    obs.log("decomposition_error", {"error": str(e)})
                # Fallback to default task
                tasks = [{"sag_id": "your-a2a-advisor-sag", "input": data}]
        else:
            # Fallback: single task
            tasks = [{"sag_id": "your-a2a-advisor-sag", "input": data}]

        # ===== Phase 2: A2A Sub-Agent Delegation =====
        results: List[Result] = []
        a2a_call_count = 0
        delegation_traces: List[Dict[str, Any]] = []

        for idx, task in enumerate(tasks):
            task_id = f"task-{uuid.uuid4().hex[:6]}"
            sag_id = task.get("sag_id", "your-a2a-advisor-sag")

            # Build A2A-enhanced context
            delegation_context = {
                "parent_run_id": obs.run_id if obs else "unknown",
                "task_index": idx,
                "total_tasks": len(tasks),
                "correlation_id": correlation_id,
                "source_agent": source_agent,
                "call_chain": a2a_context.get("call_chain", []) + ["YourA2AOrchestratorMAG"],
            }

            delegation = Delegation(
                task_id=task_id,
                sag_id=sag_id,
                input=task.get("input", {}),
                context=delegation_context,
            )

            if obs:
                obs.log(
                    "a2a_invoke_start",
                    {
                        "task_id": task_id,
                        "target": sag_id,
                        "index": idx,
                        "correlation_id": correlation_id,
                    },
                )

            delegation_start = _now_ms()

            try:
                # Invoke SAG via runner (async to avoid thread/event loop nesting)
                result = await runner.invoke_sag_async(delegation)
                results.append(result)
                a2a_call_count += 1

                delegation_duration = _now_ms() - delegation_start

                if obs:
                    obs.log(
                        "a2a_invoke_complete",
                        {
                            "task_id": task_id,
                            "target": sag_id,
                            "status": result.status,
                            "duration_ms": delegation_duration,
                            "metrics": result.metrics,
                        },
                    )

                # Record delegation trace
                delegation_traces.append(
                    {
                        "agent": sag_id,
                        "task_id": task_id,
                        "status": result.status,
                        "duration_ms": delegation_duration,
                    }
                )

                if result.status != "success":
                    if obs:
                        obs.log(
                            "a2a_invoke_failure",
                            {"task_id": task_id, "target": sag_id, "error": result.error},
                        )

            except Exception as e:
                delegation_duration = _now_ms() - delegation_start
                if obs:
                    obs.log(
                        "a2a_invoke_error",
                        {
                            "task_id": task_id,
                            "target": sag_id,
                            "error": str(e),
                            "duration_ms": delegation_duration,
                        },
                    )

                # Record failed delegation
                delegation_traces.append(
                    {
                        "agent": sag_id,
                        "task_id": task_id,
                        "status": "error",
                        "duration_ms": delegation_duration,
                        "error": str(e),
                    }
                )

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
        output: Dict[str, Any] = {}
        successful_count = sum(1 for r in results if r.status == "success")

        # Check if all delegations failed
        if successful_count == 0:
            duration_ms = _now_ms() - t0
            if obs:
                obs.log(
                    "all_a2a_delegations_failed",
                    {
                        "total_tasks": len(tasks),
                        "failed_tasks": len(results),
                        "duration_ms": duration_ms,
                        "correlation_id": correlation_id,
                    },
                )
                obs.metric("latency_ms", duration_ms)
                obs.metric("a2a_calls", a2a_call_count)
            raise RuntimeError(
                f"All {len(tasks)} A2A delegation(s) failed. Cannot generate valid output."
            )

        if skills and skills.exists("skill.result-aggregation"):
            try:
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

        # ===== Phase 4: A2A Response Formatting =====
        # Include A2A-specific metadata and tracing information
        final_output = {
            "result": {
                "status": "success",
                "data": output,
            },
            "metadata": {
                "generated_by": "YourA2AOrchestratorMAG",
                "run_id": obs.run_id if obs else f"mag-{uuid.uuid4().hex[:8]}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": "0.1.0",
                "task_count": len(tasks),
                "successful_tasks": successful_count,
                "a2a_calls": a2a_call_count,
            },
            "trace": {
                "correlation_id": correlation_id,
                "parent_agent": source_agent,
                "call_chain": a2a_context.get("call_chain", []) + ["YourA2AOrchestratorMAG"],
                "delegations": delegation_traces,
            },
        }

        # ===== Phase 5: Observability & Completion =====
        duration_ms = _now_ms() - t0
        if obs:
            obs.metric("latency_ms", duration_ms)
            obs.metric("task_count", len(tasks))
            obs.metric("success_count", successful_count)
            obs.metric("a2a_calls", a2a_call_count)
            obs.metric("a2a_success_rate", successful_count / len(tasks) if tasks else 0)

            obs.log(
                "end",
                {
                    "status": "success",
                    "duration_ms": duration_ms,
                    "tasks": len(tasks),
                    "successful": successful_count,
                    "a2a_calls": a2a_call_count,
                    "correlation_id": correlation_id,
                },
            )

        return final_output

    except Exception as e:
        # Top-level error handling
        duration_ms = _now_ms() - t0
        if obs:
            obs.log(
                "error",
                {
                    "error": str(e),
                    "type": type(e).__name__,
                    "duration_ms": duration_ms,
                    "correlation_id": payload.get("context", {}).get("correlation_id"),
                },
            )
            obs.metric("latency_ms", duration_ms)
            obs.metric("a2a_calls", a2a_call_count)
        raise
