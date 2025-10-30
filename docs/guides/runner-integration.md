---
title: Runner Integration Guide
last_synced: 2025-10-24
description: Expectations and interface requirements for runner adapters
change_log:
  - 2025-10-24: Added front-matter and structured runner requirements
---

# Runner Integration Guide

This document captures the expectations for runner adapters that integrate with AG-Driven Development (AGDD).

## Current Adapter
- **Flow Runner (`FlowRunner`)**
  - Capabilities: `dry-run`, `artifacts`
  - CLI support: `agdd cli flow available|validate|run|summarize|gate`
  - Artifacts: `.runs/<RUN_ID>/logs.jsonl`, `summary.json`, `mcp_calls.jsonl`
  - Governance: `policies/flow_governance.yaml`, validated via `agdd flow gate` or `make flow-run`

## Required Interface

All runners must implement `agdd.runners.base.Runner` and expose:

- `is_available()` - detect whether the runner can execute on the current machine.
- `validate()` - schema or contract validation with optional fallback behavior.
- `run()` - execution with support for `dry_run`, `only`, `continue_from`, `env` when available.
- `info()` - return `RunnerInfo` including name, version, and capability set.

### Capabilities
The following capability identifiers describe optional features:

- `dry-run` - supports non-destructive planning runs.
- `artifacts` - produces structured run artifacts accessible by AGDD tooling.
- `resume` - allows resuming a run from an intermediate step.
- `retries` - supports runner-managed retry policies.
- `otel-trace` - emits OpenTelemetry traces.
- `ui` - exposes a UI or dashboard for run inspection.

Adapters should advertise only the capabilities they implement. Downstream tooling may branch based on the capability set.

## Conformance Checklist

When adding a new runner adapter:

1. Implement the `Runner` protocol and `info()` method.
2. Provide a minimal example flow and schema if the runner needs bespoke definitions.
3. Ensure `src/agdd/observability/summarize_runs.py` can normalize the runner's artifacts or supply a custom normalizer.
4. Add tests under `tests/runner/conformance/` exercising:
   - `is_available()` detection (can be skipped when the runner binary is missing).
   - `validate()` error handling for known-bad inputs.
   - `run(dry_run=True)` success path.
   - `info()` capability reporting.
5. Document installation steps and environment variables in this file and `README.md`.
6. Update governance tooling if the runner outputs a different artifact format.

## Governance & Observability

- Flow summaries must conform to `src/agdd/assets/contracts/flow_summary.schema.json`.
- Vendor assets (e.g., Flow Runner schema) are locked via `tools/verify_vendor.py`.
- CI must execute the runner integration tests and publish run summaries for policy evaluation.

## Agent Runner

The **Agent Runner** (`agdd.runners.agent_runner`) orchestrates MAG (Main Agent) and SAG (Sub-Agent) execution with built-in observability.

### Key Interfaces

```python
from agdd.runners.agent_runner import invoke_mag, invoke_sag, Delegation, Result

# Invoke a Main Agent
output = invoke_mag("offer-orchestrator-mag", {"role": "Engineer", "level": "Senior"})

# Invoke a Sub-Agent
delegation = Delegation(
    task_id="task-001",
    sag_id="compensation-advisor-sag",
    input={"candidate_profile": {...}},
    context={"parent_run_id": "mag-abc123"}
)
result = invoke_sag(delegation)
```

### Capabilities
- **Dependency Injection**: Registry, skills, and runner instances injected into agent code
- **Retry Logic**: SAGs can configure retry policies with exponential backoff
- **Observability**: Automatic logging and metrics to `.runs/agents/<RUN_ID>/`, with centralized cost persistence in `.runs/costs/` and optional OpenTelemetry spans
- **Plan Awareness**: Honors `agdd.routing.router.Plan` flags for batch, cache, structured outputs, and moderation decisions
- **Error Handling**: Graceful failure handling with partial result aggregation

### Observability Artifacts

All agent executions produce structured artifacts in `.runs/agents/<RUN_ID>/`:

#### `logs.jsonl` - Event Log
JSONL format with one event per line:
```json
{"run_id": "mag-abc123", "event": "start", "timestamp": 1234567890.123, "data": {"agent": "OfferOrchestratorMAG"}}
{"run_id": "mag-abc123", "event": "delegation_start", "timestamp": 1234567891.234, "data": {"task_id": "task-001", "sag_id": "compensation-advisor-sag"}}
{"run_id": "mag-abc123", "event": "delegation_complete", "timestamp": 1234567892.345, "data": {"task_id": "task-001", "status": "success"}}
{"run_id": "mag-abc123", "event": "end", "timestamp": 1234567893.456, "data": {"status": "success", "duration_ms": 3333}}
```

**Standard Events:**
- `start` - Agent execution begins
- `delegation_start` / `delegation_complete` - SAG invocation lifecycle
- `error` - Runtime errors with type and message
- `end` - Agent execution completes

#### `metrics.json` - Performance Metrics
```json
{
  "latency_ms": 3333,
  "task_count": 2,
  "success_count": 2,
  "duration_ms": 3333
}
```

**Standard Metrics:**
- `latency_ms` (required) - Total execution time in milliseconds
- `task_count` - Number of SAG delegations
- `success_count` - Number of successful delegations
- `attempts` - Retry attempts for SAGs
- `tokens` - Token usage (if available)
- `cost` - Estimated cost (if available)

Cost ledger entries are written separately to `.runs/costs/costs.jsonl` and `.runs/costs.db` via `agdd.observability.cost_tracker`.

#### `summary.json` - Run Summary
```json
{
  "run_id": "mag-abc123",
  "agent": "OfferOrchestratorMAG",
  "status": "success",
  "start_time": 1234567890.123,
  "end_time": 1234567893.456,
  "duration_ms": 3333,
  "metadata": {
    "version": "0.1.0",
    "task_count": 2,
    "successful_tasks": 2
  }
}
```

### Observability SLO

Agent executions should meet these minimum thresholds:

| Metric | Target | Critical |
|--------|--------|----------|
| Success Rate (MAG) | ≥ 95% | ≥ 90% |
| Success Rate (SAG) | ≥ 98% | ≥ 95% |
| P95 Latency (MAG) | ≤ 5s | ≤ 10s |
| P95 Latency (SAG) | ≤ 2s | ≤ 5s |

**Note:** SLOs are measured over 24-hour rolling windows. Critical thresholds trigger alerts; below-target values require investigation.

### LLM Plan Integration

`AgentRunner` loads execution plans via `agdd.routing.router.get_plan()` and embeds the selected `Plan` snapshot in each run directory. The snapshot includes:

- `use_batch`, `use_cache`, `structured_output`, `moderation` flags
- Provider/model decisions and metadata
- Plan overrides applied at invocation time

These values are surfaced in `summary.json` metadata and recorded alongside cost events so downstream governance can audit why a batch or moderation pathway was selected. When plan flags require capabilities (e.g., batch APIs), the runner logs the decision and falls back gracefully if a provider declines support, preserving the flag state for analysis.

### Conformance
- Agents must provide `run(payload, *, registry, skills, runner, obs)` entrypoint
- MAGs orchestrate tasks via `runner.invoke_sag(delegation)`
- SAGs execute domain logic and return structured output
- All execution produces observability artifacts for governance

## Future Work

- Expand capability coverage as new runners expose richer feature sets.
- Provide sample adapters or mocks for testing runner orchestration without external dependencies.
- Add async/parallel SAG invocation for MAGs
- Implement circuit breaker patterns for failing SAGs
