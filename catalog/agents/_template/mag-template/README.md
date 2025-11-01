# YourOrchestratorMAG

**Role:** Main Agent (MAG)
**Version:** 0.1.0
**Status:** Template

## Overview

[Describe what this MAG orchestrates and its primary purpose]

## Responsibilities

- **Task Decomposition:** Break down high-level requests into sub-tasks
- **SAG Delegation:** Route tasks to appropriate sub-agents
- **Result Aggregation:** Combine SAG outputs into final response
- **Error Handling:** Manage partial failures and fallback strategies

## Input Contract

**Schema:** `contracts/your_input.schema.json`

Example:
```json
{
  "field1": "value1",
  "field2": 123
}
```

## Output Contract

**Schema:** `contracts/your_output.schema.json`

Example:
```json
{
  "result": {
    "field1": "processed_value"
  },
  "metadata": {
    "run_id": "mag-abc123",
    "timestamp": "2025-10-21T12:00:00Z",
    "task_count": 2,
    "successful_tasks": 2
  }
}
```

## Dependencies

### Sub-Agents
- `your-advisor-sag` - [Describe SAG purpose]

### Skills
- `skill.task-decomposition` - Breaks requests into tasks
- `skill.result-aggregation` - Combines SAG results

## Execution Flow

1. **Input Validation** - Validate against input schema
2. **Task Decomposition** - Identify sub-tasks
3. **SAG Delegation** - Invoke sub-agents
4. **Result Aggregation** - Combine outputs
5. **Output Formatting** - Package with metadata

See [ROUTE.md](./ROUTE.md) for detailed decision logic.

## Error Handling

- **SAG Failure:** Continue with partial results, log error
- **All SAGs Fail:** Raise error with diagnostic information
- **Skill Unavailable:** Fallback to default behavior

## Observability

All executions produce artifacts in `.runs/agents/<RUN_ID>/`:
- `logs.jsonl` - Event stream
- `metrics.json` - Performance metrics
- `summary.json` - Execution summary

## Testing

```bash
# Unit test
uv run -m pytest tests/agents/test_your_orchestrator_mag.py -v

# Integration test
echo '{"field1":"test"}' | uv run magsag agent run your-orchestrator-mag
```

## Development Notes

[Add implementation notes, known limitations, future enhancements]
