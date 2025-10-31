# AGDD v0.2 Enterprise Hardening

## Purpose / Big Picture
- Deliver v0.2 release pillars (Approval-as-a-Policy, Remote MCP Client, Durable Run, Handoff-as-a-Tool, Memory IR) with enterprise-grade safety, observability, and resilience.
- Ensure all additions respect existing IR/SPI patterns, MAG/SAG orchestration, governance, and cost-optimization philosophy.
- Maintain backward compatibility by defaulting new capabilities behind feature flags and documenting enablement paths.
- Exit criteria include green test matrix (pytest, mypy strict, ruff), updated documentation, and changelog entries for v0.2.

## Context and Orientation
- Roadmap alignment: `docs/development/roadmap.md`.
- Governance references: `catalog/policies`, `docs/architecture/agents.md`, `docs/architecture/ssot.md`.
- Runner and routing context: `src/agdd/runners/agent_runner.py`, `src/agdd/router.py`, `src/agdd/routing/router.py`.
- Storage abstractions: `src/agdd/storage/base.py`, `src/agdd/storage`.
- Catalog assets to extend: `catalog/contracts`, `catalog/policies`, `catalog/registry`.
- Branch: `feat/v0.2-enterprise-hardening`.

## Plan of Work
1. **Planning & Scaffolding**: Establish branches, feature flag scaffolds, shared utilities (permissions enums, schemas).
2. **Approval-as-a-Policy**: Implement permission evaluation, approval ticket lifecycle, API/SSE surfaces, storage schema updates.
3. **Remote MCP Client Integration**: Build async MCP client, decorators, policy defaults, configuration, resilience strategies.
4. **Durable Run Engine**: Introduce snapshot storage, runner integration, restart flows, observability hooks.
5. **Handoff-as-a-Tool Implementation**: Create tool schema, adapters, policy hooks, event instrumentation.
6. **Memory IR Layer**: Define memory IR models, storage backend, governance policies, MAG/SAG integration points.
7. **Testing & Validation**: Unit/integration coverage per pillar, feature flag toggles, SSE/API verification.
8. **Documentation & Release Readiness**: Author new docs, update README/CHANGELOG, ensure SSOT alignment.
9. **Cleanup & Final Review**: Remove deprecated logic, obsolete files, outdated docs; verify paths and references are current.

## To-do
- [ ] Planning & shared scaffolds ready (feature flags, base enums, schema placeholders).
- [ ] Approval-as-a-Policy implemented (core logic, API, storage, SSE, tests, docs).
- [ ] Remote MCP client operational with decorators, retries, policy integration, tests, docs.
- [ ] Durable Run engine with snapshots, restart handling, storage migrations, tests, docs.
- [ ] Handoff-as-a-Tool available with adapters, policies, events, tests, docs.
- [ ] Memory IR layer active with storage, governance policies, MAG/SAG integration, tests, docs.
- [ ] Full validation matrix green (pytest, pytest -m slow, mypy strict, ruff).
- [ ] Documentation set updated (new guides, README, CHANGELOG, SSOT cross-links).
- [ ] Comprehensive cleanup of legacy code, outdated logic, unused files/folders, stale docs, misaligned relative paths.

## Progress
- [2025-02-14 00:00 UTC] Plan drafted based on v0.2 enterprise hardening scope and constraints.

## Decision Log
- [2025-02-14 00:00 UTC] Adopted feature-flag-first rollout for all pillars to preserve backward compatibility and safety.

## Surprises & Discoveries
- [2025-02-14 00:00 UTC] None yet – awaiting implementation phases to surface risks.

## Concrete Steps
1. Create branch `feat/v0.2-enterprise-hardening` and ensure toolchains via `uv sync --extra production`.
2. Introduce feature flag constants and configuration plumbing in `src/agdd/api/config.py` and relevant modules.
3. Scaffold new core modules (permissions, memory, durable runner, MCP client) with type-safe foundations.
4. Extend storage schema to handle approvals, snapshots, memory entries; write migrations or setup routines.
5. Wire Approval Gate through runners, API, SSE, and governance policies.
6. Implement MCP client with retry/circuit breaking, integrate with skills runtime, update policies.
7. Build durable runner snapshotting and resume logic, ensuring idempotency and observability signals.
8. Implement handoff tool adapters and schema validations, integrate with routing/governance.
9. Add memory IR storage API, integrate into MAG/SAG flows where relevant, respect retention policies.
10. Update catalog contracts/policies and assets for new schemas and defaults.
11. Write unit/integration tests covering all new paths, including approval flows, MCP usage, durable resumes, handoff requests, memory operations.
12. Update docs (`docs/approval.md`, `docs/mcp.md`, `docs/durable-run.md`, `docs/handoff.md`, `docs/memory.md`), README highlights, and CHANGELOG for v0.2.
13. Run validation suite: `make test`, `make test-slow`, `uv run mypy src tests`, `ruff check`.
14. Final cleanup: remove deprecated code paths, obsolete configs, unused assets; confirm documentation links and relative paths.

## Validation and Acceptance
- Unit tests for permissions, approvals, MCP client, durable runner, handoff tool, memory store.
- Integration tests for approval workflow (SSE/API), remote MCP invocation (mock servers), durable run restart, cross-platform handoff, memory read/write lifecycle.
- Static analysis: `uv run mypy --strict src tests`, `ruff check src tests`.
- Runtime smoke: `uv run agdd agent run` with feature flags enabled/disabled.
- Governance validation: `uv run agdd flow gate` with updated policies.

## Idempotence and Recovery
- Approval tickets resumable via pending status and TTL checks; API supports replays without duplication.
- Durable runner snapshots allow replay from last successful step; snapshot writes are idempotent by `(run_id, step_id)`.
- MCP client employs retry limits and circuit breaker to avoid cascading failures; failures log for requeue.
- Handoff tool records requests/results permitting safe retries with unique identifiers.
- Memory IR entries include TTLs and idempotent upserts keyed by memory_id.

## Outcomes & Retrospective
- _Pending completion of implementation tasks._

## Artifacts and Notes
- Target PR: `feat(v0.2): Approval Gate, Remote MCP, Durable Run, Handoff Tool, Memory IR`.
- Expected labels: enhancement, safety, mcp, orchestration, durability, memory.
- Branch: `feat/v0.2-enterprise-hardening`.

## Interfaces and Dependencies
- Impacted APIs: FastAPI approval endpoints, SSE log stream, storage backends.
- External dependencies: MCP servers (GitHub, Stripe, Postgres), Flow Runner integration.
- Catalog updates: tool permission policies, handoff contracts, memory retention policies.
- Observability tools: OpenTelemetry spans, Langfuse integrations for new events.
