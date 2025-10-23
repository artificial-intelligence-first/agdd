---
name: task-decomposition
description: >
  Decomposes a high-level task into sub-tasks for delegation to sub-agents.
iface:
  input_schema: contracts/candidate_profile.json
  output_schema: (list of task objects)
slo:
  success_rate_min: 0.95
  latency_p95_ms: 500
---

# Task Decomposition (task-decomposition)

## Purpose
Analyzes a high-level request and breaks it down into discrete sub-tasks suitable for delegation to specialized sub-agents.

## When to Use
- A MAG needs to orchestrate multiple SAGs
- Complex workflows require parallel or sequential task execution
- Task dependencies and prerequisites need to be identified

## Procedures
1. Analyze input payload structure
2. Identify required capabilities
3. Map capabilities to available sub-agents
4. Generate task list with sag_id and input for each task

## Examples
Single task delegation to compensation-advisor-sag for salary band generation.
