# Routing Logic - YourOrchestratorMAG

## Decision Tree

```
Input: your_input
    │
    ├─→ Phase 1: Task Decomposition
    │       ├─ IF skill.task-decomposition available:
    │       │    └─→ Invoke skill → tasks[]
    │       └─ ELSE:
    │            └─→ Fallback: [default-sag]
    │
    ├─→ Phase 2: Delegation
    │       └─ FOR EACH task:
    │            ├─→ Create Delegation(task_id, sag_id, input, context)
    │            ├─→ runner.invoke_sag(delegation) → Result
    │            ├─ IF status == "success":
    │            │    └─→ Collect result
    │            └─ ELSE:
    │                 └─→ Log error, continue
    │
    ├─→ Phase 3: Aggregation
    │       ├─ IF skill.result-aggregation available:
    │       │    └─→ Invoke skill(results) → aggregated
    │       └─ ELSE:
    │            └─→ Fallback: Use first successful result
    │
    └─→ Phase 4: Output
            └─→ Wrap in output schema with metadata
```

## SAG Selection Rules

### Current (v0.1.0)
- **Default:** Route to `your-advisor-sag`
- **Reason:** Initial implementation

### Future Enhancements
[Document planned routing strategies based on input attributes]

## Error Handling

### SAG Invocation Failure
1. Log error with task_id and details
2. Continue processing remaining tasks
3. Check if all tasks failed → raise error
4. Otherwise, aggregate partial results

### Skill Failures
- **Task Decomposition:** Fallback to single-task strategy
- **Result Aggregation:** Fallback to first successful result

## Context Propagation

Every SAG delegation includes:
```python
context = {
    "parent_run_id": run_id,
    "task_index": idx,
    "total_tasks": len(tasks),
}
```

## Observability

Log all routing decisions:
```jsonl
{"event":"decomposition","task_count":N}
{"event":"delegation_start","task_id":"...","sag_id":"..."}
{"event":"delegation_complete","task_id":"...","status":"success"}
```
