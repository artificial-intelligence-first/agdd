# Routing Logic - OfferOrchestratorMAG

## Overview

This document describes the decision-making logic within OfferOrchestratorMAG for routing tasks to sub-agents and handling various execution scenarios.

## Current Routing Strategy

### Version 0.1.0 - Single SAG Pattern

**Context:** Initial implementation focuses on establishing MAG→SAG orchestration patterns with minimal complexity.

**Decision Tree:**

```
Input: candidate_profile
    │
    ├─→ Phase 1: Task Decomposition
    │       ├─ IF skill.task-decomposition available:
    │       │    └─→ Invoke skill → tasks[]
    │       └─ ELSE:
    │            └─→ Fallback: [compensation-advisor-sag]
    │
    ├─→ Phase 2: Delegation
    │       └─ FOR EACH task:
    │            ├─→ Create Delegation(task_id, sag_id, input, context)
    │            ├─→ runner.invoke_sag(delegation) → Result
    │            ├─ IF status == "success":
    │            │    └─→ Collect result
    │            └─ ELSE:
    │                 └─→ Log error, continue with partial results
    │
    ├─→ Phase 3: Aggregation
    │       ├─ IF skill.result-aggregation available:
    │       │    └─→ Invoke skill(successful_outputs) → aggregated
    │       └─ ELSE:
    │            └─→ Fallback: Return first successful result
    │
    └─→ Phase 4: Output
            └─→ Wrap in offer_packet with metadata
```

## SAG Selection Rules

### Current (v0.1.0)
- **Default:** All tasks routed to `compensation-advisor-sag`
- **Reason:** Walking skeleton - establish end-to-end flow

### Future (Planned)

#### Role-Based Routing
```
IF candidate.role IN ["Engineering", "Software Engineer"]:
    → tech-compensation-advisor-sag  # Specialized for tech roles
ELIF candidate.role IN ["Sales", "Account Executive"]:
    → sales-compensation-advisor-sag  # Commission-based logic
ELSE:
    → compensation-advisor-sag  # General-purpose
```

#### Experience-Based Routing
```
IF candidate.experience_years > 15:
    → executive-compensation-advisor-sag  # Equity-heavy packages
ELIF candidate.experience_years < 2:
    → junior-compensation-advisor-sag  # Entry-level bands
ELSE:
    → compensation-advisor-sag
```

#### Multi-SAG Orchestration
```
tasks = [
    {sag_id: "compensation-advisor-sag", input: profile},
    {sag_id: "benefits-advisor-sag", input: profile},      # Parallel
    {sag_id: "equity-advisor-sag", input: profile}         # Parallel
]
# Aggregate all three outputs into comprehensive offer packet
```

## Error Handling & Fallback

### SAG Invocation Failure

**Scenario:** `runner.invoke_sag()` throws exception or returns `status: "failure"`

**Response:**
1. Log error with `task_id`, `sag_id`, and error details
2. Continue processing remaining tasks (don't fail-fast)
3. Aggregate partial results from successful tasks
4. Include failure count in metadata

**Future Enhancement:** Retry with alternative SAG variant
```
IF compensation-advisor-sag fails:
    TRY compensation-advisor-sag-fallback (simpler logic, higher reliability)
```

### Skill Failures

#### Task Decomposition Failure
**Fallback:** Single-task strategy
```python
tasks = [{"sag_id": "compensation-advisor-sag", "input": {"candidate_profile": payload}}]
```

#### Result Aggregation Failure
**Fallback:** First successful result
```python
for result in results:
    if result.status == "success":
        return result.output
```

### Empty Results

**Scenario:** All SAG invocations fail

**Response:**
1. Log critical error
2. Raise exception to caller
3. Metadata indicates `successful_tasks: 0`

**Future:** Return default/minimal offer with warnings

## Context Propagation

Every SAG delegation includes context:
```python
context = {
    "parent_run_id": run_id,        # MAG run identifier
    "task_index": idx,               # Position in task list
    "total_tasks": len(tasks),       # Total task count
}
```

**Purpose:**
- Distributed tracing across MAG→SAG boundaries
- Observability: Link SAG logs back to parent MAG execution
- Future: Priority/deadline propagation for scheduling

## Conditional Logic (Future)

### Budget-Aware Routing
```
IF remaining_budget.tokens < 50000:
    → Use lightweight SAG variants (fewer LLM calls)
    → Skip optional enrichment tasks
```

### Policy-Gated Delegation
```
IF offer.base_salary > governance_threshold:
    → Insert approval-workflow-sag before finalization
    → Wait for human approval signal
```

### A/B Testing
```
variant = select_ab_variant("compensation-advisor", context)
IF variant == "A":
    → compensation-advisor-sag@0.1.0
ELIF variant == "B":
    → compensation-advisor-sag@0.2.0-experimental
```

## Observability Hooks

Every routing decision logged:
```jsonl
{"event":"decomposition","task_count":1,"tasks":[...]}
{"event":"delegation_start","task_id":"task-abc","sag_id":"compensation-advisor-sag"}
{"event":"delegation_complete","task_id":"task-abc","status":"success","metrics":{...}}
```

**Metrics Captured:**
- `task_count` - Number of decomposed tasks
- `delegation_latency_ms` - Per-SAG invocation time
- `success_count` - Successful SAG invocations
- `failure_count` - Failed SAG invocations

## Testing Routing Logic

### Unit Tests
```python
def test_fallback_when_decomposition_skill_unavailable():
    # Given: skills.exists("task-decomposition") returns False
    # When: MAG runs
    # Then: Single task to compensation-advisor-sag created
```

### Integration Tests
```python
def test_partial_failure_aggregation():
    # Given: 3 tasks, 2 succeed, 1 fails
    # When: MAG aggregates
    # Then: Output contains data from 2 successful tasks
    #       metadata.successful_tasks == 2
```

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-10-21 | Single SAG routing | Establish walking skeleton, defer complexity |
| 2025-10-21 | Continue on partial failures | Maximize output availability, log failures for observability |
| 2025-10-21 | Fallback strategies for skills | Ensure MAG always produces output even without optional skills |

## Future Routing Enhancements

1. **Dynamic SAG Selection** - Query registry for available SAG variants, select based on score/health
2. **Conditional Branching** - IF/THEN logic based on candidate attributes
3. **Parallel Execution** - Invoke independent SAGs concurrently (asyncio)
4. **Dependency Graphs** - Task B depends on output from Task A
5. **Circuit Breaker** - Temporarily disable failing SAGs, reroute to healthy alternatives
6. **Load Balancing** - Distribute tasks across SAG replicas for scale
