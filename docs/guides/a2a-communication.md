# Agent-to-Agent (A2A) Communication

This guide covers the Agent-to-Agent (A2A) communication patterns in AGDD, focusing on the MAG (Main Agent) and SAG (Sub-Agent) orchestration architecture.

## Overview

AGDD implements a hierarchical agent architecture where Main Agents (MAGs) orchestrate work by delegating tasks to specialized Sub-Agents (SAGs). This pattern enables:

- **Task decomposition**: Breaking complex requests into manageable subtasks
- **Specialization**: Dedicated agents for specific domains
- **Scalability**: Parallel execution of independent tasks
- **Fault tolerance**: Graceful handling of partial failures
- **Observability**: Full tracing of agent interactions

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Request                            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │      Main Agent (MAG)          │
        │   - Task decomposition         │
        │   - Delegation logic           │
        │   - Result aggregation         │
        │   - Error handling             │
        └────────────┬───────────────────┘
                     │
         ┌───────────┼───────────┬────────────┐
         │           │           │            │
         ▼           ▼           ▼            ▼
    ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
    │ SAG-1  │  │ SAG-2  │  │ SAG-3  │  │ SAG-N  │
    │(Domain │  │(Domain │  │(Domain │  │(Domain │
    │Expert) │  │Expert) │  │Expert) │  │Expert) │
    └────┬───┘  └───┬────┘  └───┬────┘  └───┬────┘
         │          │           │            │
         └──────────┴───────────┴────────────┘
                     │
                     ▼
        ┌────────────────────────────────┐
        │      Aggregated Result         │
        └────────────────────────────────┘
```

## Key Concepts

### Main Agent (MAG)

MAGs are orchestrators responsible for:

- **Task decomposition**: Breaking requests into subtasks
- **Delegation**: Routing tasks to appropriate SAGs
- **Aggregation**: Combining results from multiple SAGs
- **Error handling**: Managing failures and partial results
- **Context management**: Maintaining state across delegations

**Naming Convention**: Suffix with `-mag` (e.g., `offer-orchestrator-mag`)

### Sub-Agent (SAG)

SAGs are specialists that:

- **Execute specific tasks**: Focus on domain expertise
- **Return structured results**: Follow output contracts
- **Report metrics**: Track performance and costs
- **Handle failures gracefully**: Return errors without crashing

**Naming Convention**: Suffix with `-sag` (e.g., `compensation-advisor-sag`)

### Delegation

The `Delegation` object encapsulates task assignment:

```python
@dataclass
class Delegation:
    task_id: str           # Unique task identifier
    sag_id: str           # Target SAG slug
    input: dict           # Input payload for SAG
    context: dict         # Shared context (run_id, metadata)
```

### Result

The `Result` object encapsulates SAG output:

```python
@dataclass
class Result:
    task_id: str          # Matching delegation task_id
    status: str           # "success" or "failure"
    output: dict          # Structured output (contract-compliant)
    metrics: dict         # Performance metrics
    error: str | None     # Error message if status="failure"
```

## MAG Implementation Pattern

### Basic MAG Structure

```python
# catalog/agents/main/my-orchestrator-mag/code/orchestrator.py

from agdd.runners.agent_runner import Delegation, Result

def run(payload: dict, *, registry=None, skills=None, runner=None, obs=None) -> dict:
    """
    Main orchestrator agent.

    Args:
        payload: Input conforming to input contract
        registry: Agent/skill resolution
        skills: Skill execution runtime
        runner: Sub-agent invocation
        obs: Observability logger

    Returns:
        Output conforming to output contract
    """
    obs.log("start", {"agent": "MyOrchestratorMAG"})

    # Phase 1: Task Decomposition
    tasks = decompose_tasks(payload, skills, obs)

    # Phase 2: Delegation
    results = delegate_tasks(tasks, runner, obs)

    # Phase 3: Aggregation
    output = aggregate_results(results, skills, obs)

    # Phase 4: Finalization
    return finalize_output(output, obs)
```

### Phase 1: Task Decomposition

Break the request into subtasks:

```python
def decompose_tasks(payload: dict, skills, obs) -> list[dict]:
    """Decompose request into subtasks"""

    # Option 1: Use decomposition skill
    if skills and skills.exists("skill.task-decomposition"):
        try:
            tasks = skills.invoke("skill.task-decomposition", payload)
            obs.log("decomposition", {"task_count": len(tasks)})
            return tasks
        except Exception as e:
            obs.log("decomposition_error", {"error": str(e)})

    # Option 2: Hardcoded decomposition
    tasks = [
        {
            "sag_id": "data-analysis-sag",
            "input": {"data": payload["data"], "analysis_type": "statistical"}
        },
        {
            "sag_id": "report-generation-sag",
            "input": {"format": "pdf", "template": payload.get("template", "default")}
        }
    ]

    obs.log("decomposition", {"task_count": len(tasks), "method": "hardcoded"})
    return tasks
```

### Phase 2: Delegation

Delegate tasks to SAGs:

```python
import uuid

def delegate_tasks(tasks: list[dict], runner, obs) -> list[Result]:
    """Delegate tasks to SAGs and collect results"""
    results = []

    for idx, task in enumerate(tasks):
        task_id = f"task-{uuid.uuid4().hex[:6]}"

        delegation = Delegation(
            task_id=task_id,
            sag_id=task["sag_id"],
            input=task["input"],
            context={
                "parent_run_id": obs.run_id,
                "task_index": idx,
                "total_tasks": len(tasks)
            }
        )

        obs.log("delegation_start", {
            "task_id": task_id,
            "sag_id": delegation.sag_id,
            "index": idx
        })

        try:
            result = runner.invoke_sag(delegation)
            results.append(result)

            obs.log("delegation_complete", {
                "task_id": task_id,
                "status": result.status,
                "metrics": result.metrics
            })

        except Exception as e:
            obs.log("delegation_error", {"task_id": task_id, "error": str(e)})
            results.append(Result(
                task_id=task_id,
                status="failure",
                output={},
                metrics={},
                error=str(e)
            ))

    return results
```

### Phase 3: Aggregation

Combine results from multiple SAGs:

```python
def aggregate_results(results: list[Result], skills, obs) -> dict:
    """Aggregate results from SAG delegations"""

    # Filter successful results
    successful = [r for r in results if r.status == "success"]

    if not successful:
        obs.log("all_delegations_failed", {"total": len(results)})
        raise RuntimeError("All delegations failed")

    obs.log("aggregation_start", {
        "successful": len(successful),
        "failed": len(results) - len(successful)
    })

    # Option 1: Use aggregation skill
    if skills and skills.exists("skill.result-aggregation"):
        try:
            outputs = [r.output for r in successful]
            aggregated = skills.invoke("skill.result-aggregation", {"results": outputs})
            obs.log("aggregation", {"method": "skill", "result_count": len(outputs)})
            return aggregated
        except Exception as e:
            obs.log("aggregation_error", {"error": str(e)})

    # Option 2: Manual aggregation
    combined = {}
    for result in successful:
        combined.update(result.output)

    obs.log("aggregation", {"method": "manual", "result_count": len(successful)})
    return combined
```

## SAG Implementation Pattern

### Basic SAG Structure

```python
# catalog/agents/sub/my-advisor-sag/code/advisor.py

def run(payload: dict, *, registry=None, skills=None, runner=None, obs=None) -> dict:
    """
    Specialized sub-agent.

    Args:
        payload: Input from MAG (contract-compliant)
        registry: Agent/skill resolution
        skills: Skill execution runtime
        runner: Runner instance (for nested delegations)
        obs: Observability logger

    Returns:
        Output for MAG (contract-compliant)
    """
    obs.log("start", {"agent": "MyAdvisorSAG", "context": obs.context})

    try:
        # Execute specialized logic
        result = execute_task(payload, skills, obs)

        obs.log("success", {"result_summary": summarize(result)})
        return result

    except Exception as e:
        obs.log("error", {"error": str(e)})
        raise  # Runner will convert to Result with status="failure"
```

### SAG Best Practices

1. **Input validation**: Validate payload against input contract
2. **Clear logging**: Log key decisions and intermediate results
3. **Error handling**: Catch and log errors with context
4. **Metric reporting**: Track execution time and resource usage
5. **Output compliance**: Ensure output matches contract

```python
def run(payload: dict, **deps) -> dict:
    obs = deps['obs']

    # 1. Input validation
    required = ["candidate_profile"]
    if not all(k in payload for k in required):
        obs.log("validation_error", {"missing": [k for k in required if k not in payload]})
        raise ValueError(f"Missing required fields: {required}")

    # 2. Clear logging
    obs.log("processing", {"profile": payload["candidate_profile"]["role"]})

    # 3. Execute task
    try:
        result = deps['skills'].invoke("skill.compensation-analysis", payload)
    except Exception as e:
        # 4. Error handling
        obs.log("skill_error", {"skill": "compensation-analysis", "error": str(e)})
        raise

    # 5. Metric reporting
    obs.metric("analysis_items", len(result.get("recommendations", [])))

    # 6. Output compliance
    return {
        "compensation_details": result["details"],
        "recommendations": result["recommendations"],
        "confidence_score": result.get("confidence", 0.85)
    }
```

## Advanced Patterns

### Parallel Delegation

Execute independent tasks concurrently:

```python
import asyncio

async def delegate_parallel(tasks: list[dict], runner, obs) -> list[Result]:
    """Execute delegations in parallel"""

    async def invoke_async(task: dict, idx: int) -> Result:
        task_id = f"task-{uuid.uuid4().hex[:6]}"
        delegation = Delegation(
            task_id=task_id,
            sag_id=task["sag_id"],
            input=task["input"],
            context={"parent_run_id": obs.run_id, "index": idx}
        )

        obs.log("delegation_start", {"task_id": task_id, "sag_id": task["sag_id"]})

        # Assuming runner supports async invocation
        result = await runner.invoke_sag_async(delegation)

        obs.log("delegation_complete", {"task_id": task_id, "status": result.status})
        return result

    # Execute all tasks concurrently
    results = await asyncio.gather(*[invoke_async(t, i) for i, t in enumerate(tasks)])
    return list(results)
```

### Conditional Delegation

Choose SAGs based on runtime conditions:

```python
def select_sag(payload: dict, obs) -> str:
    """Select appropriate SAG based on payload characteristics"""

    # Route by data size
    if len(payload.get("data", [])) > 1000:
        obs.log("routing", {"sag": "large-data-sag", "reason": "data_size"})
        return "large-data-sag"

    # Route by complexity
    if payload.get("complexity", "low") == "high":
        obs.log("routing", {"sag": "expert-analysis-sag", "reason": "complexity"})
        return "expert-analysis-sag"

    # Default
    obs.log("routing", {"sag": "standard-analysis-sag", "reason": "default"})
    return "standard-analysis-sag"
```

### Cascading Delegation

SAGs can delegate to other SAGs (nested orchestration):

```python
# catalog/agents/sub/analysis-coordinator-sag/code/advisor.py

def run(payload: dict, **deps) -> dict:
    """SAG that delegates to other SAGs"""
    runner, obs = deps['runner'], deps['obs']

    # This SAG acts as a mini-orchestrator
    tasks = [
        {"sag_id": "data-cleaning-sag", "input": {"raw_data": payload["data"]}},
        {"sag_id": "feature-extraction-sag", "input": {"data": payload["data"]}}
    ]

    results = []
    for task in tasks:
        delegation = Delegation(
            task_id=f"nested-{uuid.uuid4().hex[:6]}",
            sag_id=task["sag_id"],
            input=task["input"],
            context={"parent_sag": "analysis-coordinator-sag"}
        )
        result = runner.invoke_sag(delegation)
        results.append(result)

    # Aggregate nested results
    cleaned_data = results[0].output.get("cleaned_data")
    features = results[1].output.get("features")

    return {"cleaned_data": cleaned_data, "features": features}
```

### Fallback Strategies

Handle failures with fallback SAGs:

```python
def delegate_with_fallback(task: dict, runner, obs) -> Result:
    """Try primary SAG, fall back to alternatives on failure"""

    fallback_chain = [
        "primary-sag",
        "fallback-sag-1",
        "fallback-sag-2"
    ]

    for sag_id in fallback_chain:
        delegation = Delegation(
            task_id=f"task-{uuid.uuid4().hex[:6]}",
            sag_id=sag_id,
            input=task["input"],
            context={"fallback_attempt": fallback_chain.index(sag_id)}
        )

        try:
            result = runner.invoke_sag(delegation)

            if result.status == "success":
                obs.log("fallback_success", {"sag": sag_id})
                return result
            else:
                obs.log("fallback_failed", {"sag": sag_id, "error": result.error})

        except Exception as e:
            obs.log("fallback_error", {"sag": sag_id, "error": str(e)})
            continue

    # All fallbacks failed
    raise RuntimeError("All fallback SAGs failed")
```

## Context Propagation

Share context across agent boundaries:

```python
# MAG side: Include context in delegation
delegation = Delegation(
    task_id="task-1",
    sag_id="my-sag",
    input=payload,
    context={
        "parent_run_id": obs.run_id,
        "customer_id": payload.get("customer_id"),
        "request_id": payload.get("request_id"),
        "priority": "high",
        "deadline": "2024-12-31T23:59:59Z"
    }
)

# SAG side: Access context from observability logger
def run(payload: dict, **deps) -> dict:
    obs = deps['obs']

    # Context is available via obs.context
    customer_id = obs.context.get("customer_id")
    priority = obs.context.get("priority", "normal")

    obs.log("context_received", {
        "customer": customer_id,
        "priority": priority
    })

    # Use context to adjust behavior
    if priority == "high":
        # Use faster but more expensive model
        model = "gpt-4o"
    else:
        model = "gpt-4o-mini"

    result = deps['skills'].invoke("skill.analysis", payload, model=model)
    return result
```

## Error Handling

### Partial Failure Handling

Continue with successful results when some SAGs fail:

```python
def handle_partial_failures(results: list[Result], obs) -> dict:
    """Handle partial failures gracefully"""

    successful = [r for r in results if r.status == "success"]
    failed = [r for r in results if r.status == "failure"]

    obs.log("delegation_summary", {
        "total": len(results),
        "successful": len(successful),
        "failed": len(failed)
    })

    # Decide based on success rate
    success_rate = len(successful) / len(results) if results else 0

    if success_rate == 0:
        # Complete failure
        obs.log("complete_failure", {"failed_count": len(failed)})
        raise RuntimeError("All delegations failed")

    elif success_rate < 0.5:
        # Too many failures
        obs.log("insufficient_success", {"success_rate": success_rate})
        raise RuntimeError(f"Only {success_rate:.0%} of delegations succeeded")

    else:
        # Acceptable, proceed with partial results
        obs.log("partial_success", {"success_rate": success_rate})
        return aggregate_partial_results(successful, obs)
```

### Retry Logic

Retry failed delegations:

```python
def delegate_with_retry(delegation: Delegation, runner, obs, max_retries: int = 3) -> Result:
    """Retry delegation on transient failures"""
    import time

    for attempt in range(max_retries):
        try:
            result = runner.invoke_sag(delegation)

            if result.status == "success":
                return result

            # Check if error is retryable
            if is_retryable_error(result.error):
                obs.log("retryable_error", {
                    "task_id": delegation.task_id,
                    "attempt": attempt + 1,
                    "error": result.error
                })

                # Exponential backoff
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                continue
            else:
                # Non-retryable error
                return result

        except Exception as e:
            obs.log("delegation_exception", {
                "task_id": delegation.task_id,
                "attempt": attempt + 1,
                "error": str(e)
            })

            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            else:
                raise

    # Max retries exceeded
    return Result(
        task_id=delegation.task_id,
        status="failure",
        output={},
        metrics={},
        error=f"Max retries ({max_retries}) exceeded"
    )

def is_retryable_error(error: str) -> bool:
    """Check if error is worth retrying"""
    retryable_patterns = [
        "rate limit",
        "timeout",
        "connection",
        "temporary"
    ]
    return any(pattern in error.lower() for pattern in retryable_patterns)
```

## Observability

### Delegation Tracing

Track agent interactions for debugging:

```python
# MAG logs delegation
obs.log("delegation_start", {
    "task_id": "task-abc123",
    "sag_id": "compensation-advisor-sag",
    "input_summary": {"role": payload["role"]}
})

# Runner logs invocation
obs.log("sag_invoke", {
    "sag_id": "compensation-advisor-sag",
    "run_id": "sag-def456",
    "parent_run_id": "mag-abc789"
})

# SAG logs execution
obs.log("start", {
    "agent": "CompensationAdvisorSAG",
    "parent_run_id": "mag-abc789"
})

# MAG logs completion
obs.log("delegation_complete", {
    "task_id": "task-abc123",
    "status": "success",
    "duration_ms": 1250
})
```

### Delegation Metrics

Track performance of A2A communication:

```bash
# Count delegations per MAG run
cat .runs/agents/<RUN_ID>/logs.jsonl | \
  jq 'select(.event == "delegation_start")' | wc -l

# Calculate delegation success rate
cat .runs/agents/<RUN_ID>/logs.jsonl | \
  jq 'select(.event == "delegation_complete") | .data.status' | \
  sort | uniq -c

# Average delegation latency
cat .runs/agents/<RUN_ID>/logs.jsonl | \
  jq 'select(.event == "delegation_complete") | .data.metrics.duration_ms' | \
  awk '{sum+=$1; count++} END {print sum/count}'
```

## Testing A2A Communication

### Unit Testing MAG

```python
# tests/agents/test_my_orchestrator_mag.py

import pytest
from unittest.mock import Mock
from catalog.agents.main.my_orchestrator_mag.code.orchestrator import run

def test_successful_delegation():
    """Test MAG with successful SAG delegation"""

    # Mock dependencies
    runner = Mock()
    runner.invoke_sag.return_value = Result(
        task_id="task-1",
        status="success",
        output={"result": "analysis complete"},
        metrics={"duration_ms": 500}
    )

    obs = Mock()
    obs.run_id = "mag-test-123"

    skills = Mock()
    skills.exists.return_value = False

    # Execute MAG
    payload = {"data": [1, 2, 3]}
    result = run(payload, runner=runner, obs=obs, skills=skills)

    # Assertions
    assert "result" in result
    runner.invoke_sag.assert_called_once()
    obs.log.assert_any_call("delegation_start", ...)
```

### Integration Testing

```python
# tests/integration/test_mag_sag_flow.py

def test_end_to_end_delegation(tmp_path):
    """Test full MAG→SAG orchestration"""

    # Execute MAG
    result = subprocess.run(
        ["uv", "run", "agdd", "agent", "run", "my-orchestrator-mag"],
        input='{"data": [1,2,3]}',
        capture_output=True,
        text=True
    )

    assert result.returncode == 0

    # Verify observability artifacts
    runs_dir = Path(".runs/agents")
    latest_run = max(runs_dir.glob("mag-*"), key=lambda p: p.stat().st_mtime)

    logs = (latest_run / "logs.jsonl").read_text()
    assert "delegation_start" in logs
    assert "delegation_complete" in logs
```

## Best Practices

### 1. Clear Contracts

Define explicit input/output contracts for all agents:

```yaml
# catalog/agents/sub/my-sag/agent.yaml
contracts:
  input: my_sag_input.schema.json
  output: my_sag_output.schema.json
```

### 2. Idempotency

SAGs should be idempotent when possible:

```python
def run(payload: dict, **deps) -> dict:
    """Idempotent SAG execution"""

    # Check if work already done
    cache_key = compute_cache_key(payload)
    cached = deps['cache'].get(cache_key)

    if cached:
        deps['obs'].log("cache_hit", {"key": cache_key})
        return cached

    # Execute and cache
    result = execute_task(payload, deps)
    deps['cache'].set(cache_key, result)

    return result
```

### 3. Timeout Handling

Set reasonable timeouts for delegations:

```python
import signal

def delegate_with_timeout(delegation: Delegation, runner, obs, timeout_s: int = 30):
    """Execute delegation with timeout"""

    def timeout_handler(signum, frame):
        raise TimeoutError(f"Delegation exceeded {timeout_s}s timeout")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_s)

    try:
        result = runner.invoke_sag(delegation)
        signal.alarm(0)  # Cancel alarm
        return result
    except TimeoutError as e:
        obs.log("delegation_timeout", {
            "task_id": delegation.task_id,
            "timeout_s": timeout_s
        })
        raise
```

### 4. Resource Budgeting

Track and limit resource usage across delegations:

```python
class DelegationBudget:
    def __init__(self, max_cost_usd: float, max_duration_s: int):
        self.max_cost = max_cost_usd
        self.max_duration = max_duration_s
        self.current_cost = 0.0
        self.start_time = time.time()

    def check(self, estimated_cost: float):
        # Check cost budget
        if self.current_cost + estimated_cost > self.max_cost:
            raise BudgetExceededError("Cost budget exceeded")

        # Check time budget
        elapsed = time.time() - self.start_time
        if elapsed > self.max_duration:
            raise BudgetExceededError("Time budget exceeded")

    def record(self, actual_cost: float):
        self.current_cost += actual_cost
```

### 5. Delegation Audit Trail

Maintain complete audit trail:

```python
# All delegation events are logged
obs.log("delegation_start", {...})    # When delegation begins
obs.log("delegation_complete", {...}) # When delegation completes
obs.log("delegation_error", {...})    # On delegation error

# Query delegation history
uv run agdd data search "delegation" --agent my-mag --limit 100
```

## Troubleshooting

### SAG Not Found

```bash
# Verify SAG is registered
cat catalog/registry/agents.yaml | grep my-sag

# Check SAG descriptor
ls catalog/agents/sub/my-sag/agent.yaml
```

### Delegation Timeout

```bash
# Find slow delegations
cat .runs/agents/<RUN_ID>/logs.jsonl | \
  jq 'select(.event == "delegation_complete" and .data.metrics.duration_ms > 5000)'
```

### Circular Delegation

Prevent infinite delegation loops:

```python
def delegate_safely(delegation: Delegation, runner, obs, visited: set = None):
    """Prevent circular delegations"""
    if visited is None:
        visited = set()

    if delegation.sag_id in visited:
        raise RuntimeError(f"Circular delegation detected: {delegation.sag_id}")

    visited.add(delegation.sag_id)
    return runner.invoke_sag(delegation, visited=visited)
```

## Related Documentation

- [Agent Development Guide](./agent-development.md) - Building MAG/SAG agents
- [Multi-Provider Guide](./multi-provider.md) - LLM provider configuration
- [Cost Optimization](./cost-optimization.md) - Managing delegation costs
- [MCP Integration](./mcp-integration.md) - Tool access for agents

## References

- [Agent Templates](../../catalog/agents/_template/) - MAG/SAG templates
- [Example MAG](../../catalog/agents/main/offer-orchestrator-mag/) - Reference implementation
- [Example SAG](../../catalog/agents/sub/compensation-advisor-sag/) - Reference implementation
- [SSOT](../reference/ssot.md) - Terminology and policies
