# Runner Integration Guide

This document captures the expectations for runner adapters that integrate with AG-Driven Development (AGDD).

## Current Adapter
- **Flow Runner (`FlowRunner`)**
  - Capabilities: `dry-run`, `artifacts`
  - CLI support: `agdd cli flow available|validate|run|summarize|gate`
  - Artifacts: `.runs/<RUN_ID>/runs.jsonl`, `summary.json`, `mcp_calls.jsonl`
  - Governance: `policies/flow_governance.yaml`, validated via `agdd.cli flow gate` (or `tools/gate_flow_summary.py`)

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
3. Ensure `observability/summarize_runs.py` can normalize the runner's artifacts or supply a custom normalizer.
4. Add tests under `tests/runner/conformance/` exercising:
   - `is_available()` detection (can be skipped when the runner binary is missing).
   - `validate()` error handling for known-bad inputs.
   - `run(dry_run=True)` success path.
   - `info()` capability reporting.
5. Document installation steps and environment variables in this file and `README.md`.
6. Update governance tooling if the runner outputs a different artifact format.

## Governance & Observability

- Flow summaries must conform to `contracts/flow_summary.schema.json`.
- Vendor assets (e.g., Flow Runner schema) are locked via `tools/verify_vendor.py`.
- CI must execute the runner integration tests and publish run summaries for policy evaluation.

## Future Work

- Expand capability coverage as new runners expose richer feature sets.
- Provide sample adapters or mocks for testing runner orchestration without external dependencies.
