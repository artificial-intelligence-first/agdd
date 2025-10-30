---
name: task-decomposition
description: >
  Decomposes a high-level task into sub-tasks for delegation to sub-agents.
iface:
  input_schema: catalog/contracts/candidate_profile.schema.json
  output_schema: list of delegation objects (`{"sag_id": str, "input": dict}`)
slo:
  success_rate_min: 0.95
  latency_p95_ms: 500
---

# Task Decomposition (task-decomposition)

## Purpose
Transform a candidate-facing payload into the minimal set of sub-agent delegations required by the orchestration workflow.

## When to Use
- A MAG needs to hand off compensation analysis to `compensation-advisor-sag`.
- The caller expects deterministic task lists without branching logic.

## Procedures
1. Normalize the input payload. When the caller supplies `candidate_profile`, reuse it as-is; otherwise treat the entire payload as the profile.
2. Emit a single delegation object targeting `compensation-advisor-sag`.
3. Allow downstream logic to expand into more complex task graphs (future enhancement).

## Examples
`{"candidate_profile": {...}}` → `[{"sag_id": "compensation-advisor-sag", "input": {"candidate_profile": {...}}}]`
