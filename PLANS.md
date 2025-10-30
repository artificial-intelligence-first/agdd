---
title: AGDD Core Refinement Plan (90 days)
slug: core-refinement
status: proposed
last_synced: 2025-10-30
tags: [agdd, execplan, kernel, spi, roadmap]
description: "Sharpen AGDD into a simple, scalable, future-proof core by splitting kernel and plugins, unifying planning and provider SPI, and standardizing contracts."
sources:
  - { id: S1, title: "AGDD SSOT", url: "docs/architecture/ssot.md", accessed: "2025-10-30" }
  - { id: S2, title: "ExecPlan Convention", url: "docs/architecture/plans.md", accessed: "2025-10-30" }
  - { id: S3, title: "SSOT (Upstream)", url: "https://github.com/artificial-intelligence-first/ssot", accessed: "2025-10-30" }
---

# TL;DR (Shortest Path)

- Do (P0): Split core into a small kernel with SPI, move all integrations to plugins. Introduce Run IR (intermediate representation), stable event schema, Idempotency/RBAC/Audit as defaults.
- Strengthen (P0): Normalize model features behind a Provider SPI (function/tool-calling, JSON output, vision/audio). Merge Router into a single Planner. Fix moderation at canonical control points.
- Extend (P1): Catalog Schema & Migration (versioning/compat/deprecations), Deterministic/Replay modes with event sourcing for runs, minimal bench harness.
- Trim (P1/P2): Everything outer-ring becomes a plugin (Flowctl, GitHub Webhook, Langfuse, Redis/FAISS impl details). Minimize the supported surface area of the kernel.

# Architectural Principles

1) Kernel is sacred (small, stable, low deps)
2) Everything is a plugin (via SPI)
3) Contracts over code (Schema/Protocol ensure stability)
4) Determinism first (reproducibility is operational safety)
5) Secure-by-default (Idempotency/RBAC/Audit/Moderation on by default)

# Strategy: Do / Strengthen / Extend / Trim

## Do (P0) — Immediate, decisive steps

1. Package split: `agdd-core` and `agdd-plugins-*`
   - Core: Run IR / Agent Runner / Read-only Registry / Provider SPI / Observability SPI / Policy SPI / Stable Error & Event schema / API middleware (Idempotency, RBAC scopes, Audit, RateLimit)
   - Plugins: `openai|anthropic|google|ollama`, `router-basic`, `cache-faiss|redis`, `telemetry-otel|langfuse`, `flowctl`, `github-webhook`, `storage-postgres|sqlite` (impl details)
   - Rework extras in pyproject to “core-min + optional plugins”. CI matrix: core → plugins; detect ABI breaks.

2. Run IR for unified entry (CLI/HTTP/MCP)
   - All entry points construct a `RunIR` and pass to Runner to eliminate branching.
   - Snapshot policy and capabilities at submission time.

3. Provider SPI with capability normalization
   - Unify function/tool-calling, JSON mode, vision/audio, role semantics.
   - Structured output accepted via JSON Schema; unknown models validated post-hoc in core.

4. Router → Planner (single responsibility)
   - Planner generates `PlanIR` from task traits (SLA, cost, length, sensitivity) + capability matrix.
   - Runtime downgrades emitted as `PlanDiff` events for auditability.

5. Moderation control points
   - Hooks at: Ingress (user input), Model output, Egress (external I/O). Default = fail-closed; fail-open requires audit event.

6. API defaults
   - Idempotency-Key for POST runs; RBAC scopes: `agents:run`, `runs:read`, `runs:logs`.
   - Audit fields: caller, IP, run_id, plan hash, policy snapshot, moderation decisions.
   - Webhook signature + replay guard (ts+tolerance). CORS closed by default.

## Strengthen (P0–P1) — Specs and compatibility

1. Stable Event/Error/Artifact schemas
   - EventEnvelope v1: `ts, run_id, span_id, type, payload, level, kv`.
   - Error taxonomy: `AGDD-INPUT`, `AGDD-POLICY`, `AGDD-MODERATION`, `AGDD-PROVIDER(RETRIABLE|FATAL)`, `AGDD-STORE`, …
   - Artifacts directory invariant: `runs/{run_id}/{logs.jsonl, summary.json, metrics.json, costs.jsonl, plan.json}`.

2. Catalog Schema / Versioning / Migration
   - Every `catalog/*/*.yaml` annotated with `$schema` and `version`.
   - `agdd catalog validate` (JSON Schema), `agdd catalog migrate --from vX --to vY`.
   - Deprecations with windows and auto-migrations.

3. Deterministic and Replay modes
   - `--deterministic`: fixed seed, temp=0, fixed tool ordering, fixed timestamps.
   - `--replay {run_id}`: re-run with identical Plan, input, env hash.
   - Providers must log non-deterministic metadata (model snapshots, lib versions) to `summary.json`.

4. Observability baseline
   - Core depends on OTel API only (optional); vendor backends via plugins.
   - Standardized span/run attributes: `run_id, plan_id, agent, model, cache_hit, cost_input_tokens, cost_output_tokens, policy_version`.

## Extend (P1) — Investment areas

1. Benchmarks and regression
   - Small, representative task set (classification, tool use, long-form, structured output).
   - `agdd bench run --matrix "{provider}x{model}"` outputs cost/quality/latency; feed Planner learning.

2. Safer semantic cache
   - Cache key: `hash(template_id, tool_specs, schema, capability_set, redaction_version)`.
   - TTL by sensitivity/length; light re-check on hit (e.g., low-cost model to confirm; anomaly via KL divergence).

3. SLOs and resilience
   - Declare SLOs for success rate/latency/cost; track error budgets.
   - Adaptive concurrency + circuit breakers in core; overload policies emit `PlanDiff` (downgrade, batch, cutoff).

## Trim (P1–P2) — Narrow the kernel

- Flow Runner: core only emits `PlanIR`; external orchestrators as plugins (Flowctl/Prefect/Airflow).
- GitHub Webhook: move to plugin/example; core keeps `POST /runs`.
- Observability vendors (Langfuse): plugin-only.
- Storage impl details (SQLite/Postgres): plugins; core holds interfaces and event schemas only.
- Model-specific prompt tricks: remain inside provider plugins; not in core.

# Key Interfaces (Draft)

```python
from pydantic import BaseModel
from typing import Optional, Literal, Any

class CapabilityMatrix(BaseModel):
    tools: bool
    structured_output: bool
    vision: bool
    audio: bool

class PolicySnapshot(BaseModel):
    id: str
    version: str
    content_hash: str

class PlanIR(BaseModel):
    chain: list[dict]              # ordered fallback steps
    provider: str
    model: str
    use_batch: bool
    use_cache: bool
    structured_output: bool
    moderation: bool
    sla_ms: int
    cost_budget: Optional[float]

class RunIR(BaseModel):
    run_id: str
    agent: str
    input: dict[str, Any]
    plan: Optional[PlanIR]
    policy: PolicySnapshot
    capabilities: CapabilityMatrix
    idempotency_key: Optional[str]
    trace_id: str

class Provider(Protocol):
    def capabilities(self) -> CapabilityMatrix: ...
    async def generate(self, prompt: dict, tools: list[dict] = [], *,
                       mode: Literal["text","vision","audio"] = "text",
                       schema: Optional[dict] = None) -> dict: ...
    async def batch(self, items: list[dict]) -> list[dict]: ...
```

# API Surface (Backward-compatible minimal set)

- `POST /runs` (agent, input, idempotency_key) → run_id
- `GET /runs/{run_id}` (summary, plan, status, policy_snapshot)
- `GET /runs/{run_id}/events` (JSON Lines; `since` supported)
- Keep `POST /agents/{slug}/run` for compatibility; internally delegate to `/runs`
- Scopes: `runs:create | runs:read | events:read`

# Catalog: Schemas and Migration

- Keep versioned schemas under `catalog/_schemas/*.json` and enforce via CI with `agdd catalog validate`.
- Canonical: `agent.schema.json`, `skill.schema.json`, `policy.schema.json`, `routing.schema.json`, `eval.schema.json`.
- Record breaking changes with deprecation windows and auto-migrations in the same PR; log in SSOT.

# Determinism & Replay (Acceptance Targets)

- Deterministic run outputs (ignoring timestamps/ids) under fixed seeds and temp=0.
- Replay reproduces identical `plan.json` and identical provider responses where feasible; diff tolerance documented.

# Benchmarks (Minimal Harness)

- `make bench` → HTML with three axes: quality, cost, latency.
- Golden tests: `tests/golden/{agent}/input.json` → `expected/*.json`.

# Security & Operations

- RBAC scopes fixed; audit events adhere to Event schema.
- Secrets SPI for provider/storage/telemetry plugins; mask in logs and cost trackers.
- SLOs and alerts: success rate threshold, p95 latency, provider failure rate, moderation blocks surge.

# Parallel Workstreams (No Timeline)

Run these in parallel. Each workstream defines its own non-overlapping file touch set and clear interfaces to avoid conflicts.

## WS-01 Core IR & SPI Types
- Scope: Define core types (`RunIR`, `PlanIR`, `CapabilityMatrix`, `PolicySnapshot`) and SPI stubs (Provider/Observability/Policy) without wiring.
- Create only:
  - `src/agdd/core/__init__.py`
  - `src/agdd/core/types.py`
  - `src/agdd/core/spi/__init__.py`
  - `src/agdd/core/spi/provider.py`
  - `src/agdd/core/spi/observability.py`
  - `src/agdd/core/spi/policy.py`
- Interfaces: Frozen Pydantic models; Protocols with docstrings; no external imports beyond stdlib+pydantic.
- No-go: Do not modify existing runner/router/providers.
- Done: Types importable without side effects; mypy/ruff clean.

-## WS-02 Planner Facade (Router Compatibility)
- Scope: Introduce `agdd.planner` facade that wraps existing Router to emit `PlanIR`. Do not write artefacts here.
- Create/update only:
  - `src/agdd/planner/__init__.py`
  - `src/agdd/planner/planner.py`
- Interfaces: `get_planner()`, `Planner.plan(task_traits) -> PlanIR`.
- No-go: Do not remove/rename existing router functions; no runner edits.
- Done: Unit test stub passes; existing router still works.

## WS-03 API: POST /runs + Idempotency/RBAC/Audit
- Scope: Add `POST /api/v1/runs` endpoint; add idempotency middleware; keep `/agents/{slug}/run` delegating to `/runs`.
- Create/update only:
  - `src/agdd/api/routes/runs_create.py` (new endpoint)
  - `src/agdd/api/server.py` (include router, register middleware)
  - `src/agdd/api/middleware/idempotency.py`
  - `src/agdd/api/security.py` (RBAC scopes helper, append-only)
- Interfaces: Request `{agent, payload, idempotency_key?}`; Response `{run_id}`.
- No-go: No changes to runner; no breaking changes to existing endpoints.
- Done: curl creates a run and is deduped by identical key+payload.

## WS-04 Moderation Control Points
- Scope: Define three hooks (ingress/model-output/egress) and wire them behind feature flags; emit `moderation.checked` events.
- Create/update only:
  - `src/agdd/moderation/hooks.py`
  - `src/agdd/runners/agent_runner.py` (append-only: call hooks; guarded by env/settings)
- Interfaces: `check_ingress(payload)`, `check_model_output(text)`, `check_egress(artefact)` return decision objects.
- No-go: Do not change existing moderation service signatures.
- Done: Hooks callable; events appear in logs when enabled.

## WS-05 Stable Event/Error/Artifact Schemas
- Scope: Add JSON Schemas only (no logger edits). Artefact writers live in WS-12.
- Create/update only:
  - `src/agdd/assets/schemas/event.schema.json`
  - `src/agdd/assets/schemas/error.schema.json`
  - `src/agdd/assets/schemas/artifacts.schema.json`
- Interfaces: `EventEnvelope v1` fields fixed.
- No-go: No breaking changes to current log structure; only additive.
- Done: JSON Schemas validate sample outputs.

## WS-06 Catalog Schemas & CLI (validate/migrate)
- Scope: Define catalog schemas and add CLI commands to validate and scaffold migrations.
- Create/update only:
  - `catalog/_schemas/agent.schema.json`
  - `catalog/_schemas/skill.schema.json`
  - `catalog/_schemas/policy.schema.json`
  - `catalog/_schemas/routing.schema.json`
  - `catalog/_schemas/eval.schema.json`
  - `src/agdd/cli_catalog.py` (new Typer app mounted under `agdd catalog`)
  - `src/agdd/cli.py` (append-only to add sub-commands)
- Interfaces: `agdd catalog validate`, `agdd catalog migrate --from vX --to vY` (stub).
- No-go: Do not mutate existing catalog files in this PR.
- Done: Validation runs in CI; migration prints plan (no writes).

## WS-07 Provider SPI Adapters (Scaffold)
- Scope: Implement adapters that map current providers to SPI without moving packages.
- Create/update only:
  - `src/agdd/providers/adapters/__init__.py`
  - `src/agdd/providers/adapters/openai_adapter.py`
  - `src/agdd/providers/adapters/anthropic_adapter.py`
  - `src/agdd/providers/adapters/google_adapter.py`
- Interfaces: `Provider` Protocol conformity; capability matrix; structured output passthrough.
- No-go: No deletion/rename in `src/agdd/providers/*`.
- Done: Smoke tests instantiate adapters and call `generate()` in mock.

## WS-08 Determinism & Replay Hooks
- Scope: Introduce deterministic mode and replay command surfaces without deep rewiring. Artefact snapshots wired via WS-12 helpers when available.
- Create/update only:
  - `src/agdd/runner_determinism.py` (seed/temp/tool-order helpers)
  - `src/agdd/cli.py` (append-only flags `--deterministic`, `--replay` for agent run)
- Interfaces: Deterministic toggles; `--replay <run_id>` reuses stored plan/input.
- No-go: Do not change business logic of agents/skills.
- Done: Flag toggles reflected in summary and behaviour (e.g., temp=0).

## WS-09 RBAC Scope Checks
- Scope: Add simple scope enforcement on API routes.
- Create/update only:
  - `src/agdd/api/security.py` (append-only: `require_scope(scopes: list[str])`)
  - Route decorators use `Depends(require_scope([...]))` on sensitive endpoints.
- Interfaces: Scopes provided via env or static map.
- No-go: Breaking auth flows.
- Done: Requests without scopes receive 403 in a test.

## WS-10 Semantic Cache Key Normalization
- Scope: Add canonical cache key computation and TTL policy helper.
- Create/update only:
  - `src/agdd/cache/key.py`
  - `src/agdd/cache/policy.py`
- Interfaces: `compute_key(template_id, tool_specs, schema, caps, redaction_ver)`; TTL from policy.
- No-go: Do not integrate with runtime in this change.
- Done: Unit tests cover hashing and TTL selection.

## WS-11 Bench Harness & Golden Tests Skeleton
- Scope: Minimal bench runner and golden test layout (no provider calls).
- Create/update only:
  - `benchmarks/harness.py`
  - `tests/golden/README.md`
  - `tests/golden/sample_agent/input.json`
  - `tests/golden/sample_agent/expected/output.json`
- Interfaces: `make bench` placeholder script.
- No-go: None beyond new files.
- Done: CI artifact generation smoke passes.

## WS-12 Observability Helpers (Single Owner)
- Scope: Centralize all logger append-only enhancements to avoid conflicts; add writers for `plan.json`, event envelopes, env hash snapshot.
- Update only:
  - `src/agdd/observability/logger.py`
- Interfaces: `write_plan(plan: dict)`, `log_event_envelope(event: dict)`, `snapshot_env_hash() -> str`.
- No-go: No changes to existing method signatures; only additive helpers.
- Done: Existing code unaffected; helpers used by other WS once merged.

# Plan of Work

Phases: Kernel split → SPI adoption → Entry unification (Run IR) → Observability/Audit stabilization → Catalog schema tooling → Determinism/Replay → Planner upgrades → Bench and SLOs → Outer-ring pluginization.

# Concrete Steps (Initial)

1. Define `PlanIR`, `RunIR`, and Provider SPI types in `agdd-core`.
2. Add `/runs` endpoint and Idempotency middleware; make `/agents/{slug}/run` a thin delegator.
3. Move OpenAI/Anthropic/Google/Ollama providers to `agdd-plugins-*` and adapt to SPI.
4. Implement Planner façade replacing Router usage sites; emit `plan.json` and `PlanDiff` events.
5. Introduce Moderation hooks at ingress/model-output/egress with audit logs.
6. Create catalog schemas and `agdd catalog validate/migrate` commands.

# Validation and Acceptance

- Tests
  - `uv run -m pytest -q` (fast) and slow suite gates for provider plugins
  - Golden tests compare normalized outputs under `--deterministic`
  - Catalog validation in CI must pass for all changed assets
- Governance
  - `agdd flow gate` passes thresholds (success rate, latency, required steps)
- API
  - Idempotency: same key+payload yields same run; conflict on different payload

# Idempotence and Recovery

- Idempotency store pluggable (memory/Redis). TTL defaults to 24h.
- Replay uses stored `plan.json`, input, env hash; rollback by version pinning provider plugins.

# Decision Log

- [TODO] Record renames (Router→Planner), SPI boundaries, schema IDs, and migration windows.

# Progress

- [TODO] Timestamped updates (UTC) as milestones complete.

# Surprises & Discoveries

- [TODO] Document blockers, provider API shifts, performance regressions, and mitigation.

# Artifacts and Notes

- PRs, run IDs, dashboards, and design diagrams to be linked here.

# Interfaces and Dependencies

- Services/APIs: Provider SDKs, Redis/Postgres (plugins), OTel exporters (plugins)
- Schemas: Catalog JSON Schemas; Event/Error/Artifact v1
- Teams: Core platform, Integrations, Infrastructure/DevOps

---
References: SSOT is authoritative for terminology and policies (docs/architecture/ssot.md). Align new contracts and SPI definitions with SSOT and update it alongside this plan.
