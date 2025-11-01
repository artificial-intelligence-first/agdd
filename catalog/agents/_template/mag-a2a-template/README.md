# YourA2AOrchestratorMAG

**Role:** Main Agent (MAG) with A2A Support
**Version:** 0.1.0
**Status:** Template

## Overview

This is an A2A-enabled (Agent-to-Agent) orchestrator template that supports:
- **Discovery:** Agents can discover this orchestrator via API (`GET /api/v1/agents`)
- **Invocation:** Agents can invoke this orchestrator via API (`POST /api/v1/agents/{slug}/run`)
- **Delegation:** This orchestrator delegates tasks to sub-agents (SAGs)
- **Aggregation:** Results from multiple agents are combined into a unified response

## A2A Capabilities

### Discovery
This agent can be discovered via the agent registry API:
```bash
curl http://localhost:8000/api/v1/agents
```

Response includes:
```json
{
  "slug": "your-a2a-orchestrator-mag",
  "title": "YourA2AOrchestratorMAG",
  "description": "A2A-enabled Main Agent for orchestrating agent-to-agent workflows"
}
```

### Invocation
This agent can be invoked via API by other agents or external systems:
```bash
curl -X POST http://localhost:8000/api/v1/agents/your-a2a-orchestrator-mag/run \
  -H "Content-Type: application/json" \
  -d '{"field1": "value1", "field2": 123}'
```

## Responsibilities

- **Task Decomposition:** Break down high-level requests into sub-tasks
- **A2A Coordination:** Coordinate with other agents via API calls
- **SAG Delegation:** Route tasks to appropriate sub-agents
- **Result Aggregation:** Combine outputs from multiple agents
- **Error Handling:** Manage partial failures and fallback strategies

## Input Contract

**Schema:** `contracts/a2a_orchestrator_input.schema.json`

Example:
```json
{
  "request_type": "process_workflow",
  "data": {
    "field1": "value1",
    "field2": 123
  },
  "context": {
    "source_agent": "caller-agent-id",
    "correlation_id": "abc-123"
  }
}
```

## Output Contract

**Schema:** `contracts/a2a_orchestrator_output.schema.json`

Example:
```json
{
  "result": {
    "status": "success",
    "data": {
      "processed_field": "processed_value"
    }
  },
  "metadata": {
    "run_id": "mag-abc123",
    "timestamp": "2025-10-24T12:00:00Z",
    "task_count": 2,
    "successful_tasks": 2,
    "a2a_calls": 3
  },
  "trace": {
    "parent_agent": "caller-agent-id",
    "correlation_id": "abc-123",
    "delegations": [
      {
        "agent": "your-a2a-advisor-sag",
        "status": "success",
        "duration_ms": 150
      }
    ]
  }
}
```

## Dependencies

### Sub-Agents
- `your-a2a-advisor-sag` - A2A-enabled specialist agent

### Skills
- `skill.task-decomposition` - Breaks requests into tasks
- `skill.result-aggregation` - Combines agent results

## Execution Flow

1. **API Request Reception** - Receive request via POST /api/v1/agents/{slug}/run
2. **Input Validation** - Validate against input schema
3. **Task Decomposition** - Identify sub-tasks and target agents
4. **A2A Delegation** - Invoke sub-agents via runner (supports API-based invocation)
5. **Result Aggregation** - Combine outputs from all agents
6. **Output Formatting** - Package with metadata and trace information

See [ROUTE.md](./ROUTE.md) for detailed decision logic.

## A2A Communication Patterns

### Pattern 1: Direct Delegation
```python
# MAG delegates to SAG via runner
delegation = Delegation(
    task_id="task-1",
    sag_id="your-a2a-advisor-sag",
    input=task_input,
    context={"parent_run_id": run_id}
)
result = runner.invoke_sag(delegation)
```

### Pattern 2: API-based Invocation (Future)
```python
# MAG invokes another MAG via HTTP API
response = http_client.post(
    "http://localhost:8000/api/v1/agents/other-mag/run",
    json=payload
)
```

## Error Handling

- **SAG Failure:** Continue with partial results, log error
- **All SAGs Fail:** Raise error with diagnostic information
- **Skill Unavailable:** Fallback to default behavior
- **A2A Communication Failure:** Retry with exponential backoff (if configured)

## Observability

All executions produce artifacts in `.runs/agents/<RUN_ID>/`:
- `logs.jsonl` - Event stream (includes A2A tracing)
- `metrics.json` - Performance metrics (includes A2A call counts)
- `summary.json` - Execution summary

### A2A-Specific Events
```jsonl
{"event":"a2a_discovery","agent":"your-a2a-advisor-sag","discovered":true}
{"event":"a2a_invoke_start","target":"your-a2a-advisor-sag","task_id":"task-1"}
{"event":"a2a_invoke_complete","target":"your-a2a-advisor-sag","status":"success","duration_ms":150}
```

## Testing

### Unit Test
```bash
uv run -m pytest tests/agents/test_your_a2a_orchestrator_mag.py -v
```

### Integration Test - Discovery
```bash
# Start the API server
uv run magsag api

# Test discovery endpoint
curl http://localhost:8000/api/v1/agents | jq '.[] | select(.slug == "your-a2a-orchestrator-mag")'
```

### Integration Test - Invocation
```bash
# Test invocation endpoint
curl -X POST http://localhost:8000/api/v1/agents/your-a2a-orchestrator-mag/run \
  -H "Content-Type: application/json" \
  -d @test_payload.json | jq
```

### E2E Test
```bash
# Test full discovery → invoke flow
uv run -m pytest tests/integration/test_a2a_e2e.py -v
```

## Development Notes

### Customization Checklist
- [ ] Update agent.yaml with correct slug, name, and description
- [ ] Define input/output contracts in catalog/contracts/
- [ ] Implement orchestration logic in code/orchestrator.py
- [ ] Add A2A-specific error handling
- [ ] Implement retry logic for A2A calls
- [ ] Add comprehensive tests
- [ ] Document A2A communication patterns
- [ ] Configure observability for A2A tracing

### Future Enhancements
- Support for async A2A invocation
- Circuit breaker for failing agents
- Load balancing across multiple agent instances
- A2A authentication and authorization
- Request/response caching
