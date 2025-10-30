---
title: AG-Driven Development (AGDD) Framework Hardening ExecPlan
last_synced: 2025-10-24
source_of_truth: https://github.com/artificial-intelligence-first/ssot/blob/main/topics/PLANS.md
description: Living document tracking governance, release, and documentation hardening
change_log:
  - 2025-10-24: Added front-matter and SSOT PLANS reference
---

# AG-Driven Development (AGDD) Framework Hardening ExecPlan

**Note:** For canonical ExecPlan format and planning guidelines, refer to [PLANS.md in SSOT](https://github.com/artificial-intelligence-first/ssot/blob/main/topics/PLANS.md).

This ExecPlan is a living document. Keep Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective current as work proceeds.

## Purpose / Big Picture
Anchor the AG-Driven Development (AGDD) repository around a resilient, AI-first walking skeleton so subsequent feature work inherits proven governance, observability, and packaging practices from day one.

## To-do
### Governance and Policy
- [ ] Document the upgrade path for alternative runner adapters (Temporal, LangGraph, bespoke adapters) so governance gates remain compatible.
- [ ] Expand policy coverage to include skill manifest validation and security posture checks before scaling the agent catalog.

### Release and Operations
- [ ] Establish a documented release cadence for mirrored Flow Runner assets and JSON Schemas, including automation hooks.
- [ ] Publish contributor-facing runbooks for syncing Flow Runner sample assets when upstream tags change.

### Documentation Hygiene
- [ ] Cross-link ExecPlan expectations from `README.md`, `AGENTS.md`, and contributor docs.
- [ ] Capture validation guidance in `CHANGELOG.md` and `SSOT.md` as features graduate from this plan.

## Progress
- [2025-10-23 02:30 UTC] Hardened typing and fixtures across runners, registry, governance gate, and API tests; added stub packages so `mypy --strict` succeeds alongside pytest/ruff checks.
- [2025-10-21 07:40 UTC] Refactored ExecPlan to the ExecPlans template, migrated historical accomplishments, and identified remaining governance hardening tasks.
- [2025-10-20 15:30 UTC] Walking skeleton validated end-to-end (registry lookup → schema validation → Flow Runner invocation) with automation tests and documentation updates.
- [2025-10-20 13:45 UTC] Flow Runner adapter, CLI entry points, and mirrored assets integrated with packaging configuration and smoke-test guidance.
- [2025-10-20 11:55 UTC] Governance gate operationalized via `tools/gate_flow_summary.py`, wired into CI alongside Flow Runner validation and Multi-Agent Governance checks.
- [2025-10-20 11:10 UTC] Observability summary tooling created for Flow Runner `.runs/`, exposing per-step metrics and MCP call counts.
- [2025-10-20 10:40 UTC] Baseline repository skeleton established with `uv` tooling, initial directories, and core documentation.

## Surprises & Discoveries
- [2025-10-20 16:05 UTC] Packaging smoke tests revealed missing mirrored assets; resolved by extending `uv build` guidance and ensuring wheel includes Flow Runner fixtures.

## Decision Log
- [2025-10-20 12:15 UTC] Prioritized delivering an AI & AI Agent-first walking skeleton before expanding feature depth to guarantee future agents inherit validated governance flows.

## Outcomes & Retrospective
Framework deliverables are in place with passing tests and policy checks, ready for iterative enhancements to governance coverage and release operations.

## Context and Orientation
- Repository: `agdd` (feature lineage: `feat/bootstrap-agdd`).
- Core directories: `src/agdd/`, `catalog/`, `ops/`, `docs/`.
- Supporting documentation: `docs/guides/agent-development.md`, `README.md`, `SSOT.md`, `docs/development/changelog.md`.

## Plan of Work
1. **Stabilize Governance Spine** – Formalize adapter upgrade guidance and extend policy coverage.
2. **Operationalize Release Cadence** – Define and automate Flow Runner asset/schema sync workflows.
3. **Harden Documentation Loop** – Ensure ExecPlan practices feed back into contributor onboarding materials.

## Concrete Steps
1. Draft adapter upgrade guide covering Temporal and LangGraph prototypes; store under `docs/` with cross-references from `docs/guides/agent-development.md`.
2. Flow Runner setup is now automated via `ops/scripts/setup-flowrunner.sh` (run with `make setup-flowrunner`).
3. Extend policy validation scripts to lint skill manifests and enforce security posture; add pytest coverage in `tests/governance/`.
4. Update contributor documentation to reference ExecPlan lifecycle and validation expectations.

## Validation and Acceptance
- [ ] `uv run -m pytest -q`
- [ ] `uv run python ops/tools/check_docs.py`
- [ ] `echo '{"role":"Engineer","level":"Mid"}' | uv run agdd agent run offer-orchestrator-mag`
- [ ] `uv run agdd flow available`
- [ ] `uv run agdd flow summarize --output /tmp/summary.json`
- [ ] `uv run agdd flow gate /tmp/summary.json`
- [ ] `uv build` (smoke test packaging when bundled resources change)

## Idempotence and Recovery
- Flow Runner asset sync scripts must be rerunnable; guard file operations with existence checks.
- Governance policy updates should include rollback instructions (`git checkout -- catalog/policies/flow_governance.yaml`).
- Maintain disposable virtual environments for packaging smoke tests to avoid contaminating the primary dev environment.

## Artifacts and Notes
- Policy definitions: `catalog/policies/flow_governance.yaml`.
- Governance tooling: `src/agdd/observability/summarize_runs.py`, CLI command `agdd flow gate`.
- Runner scripts: `ops/scripts/setup-flowrunner.sh` (generates `ops/scripts/flowrunner-env.sh`).
- Agent templates: `catalog/agents/_template/mag-template/` and `catalog/agents/_template/sag-template/`.
- Development automation: `Makefile` with common tasks.
- Historical progress captured in this ExecPlan; future PRs must reference relevant sections.

## Interfaces and Dependencies
- Flow Runner CLI (`agdd.cli.flow`) for workflow execution.
- Agent Runner (`agdd.runners.agent_runner`) for MAG/SAG orchestration.
- Agent registry (`catalog/registry/agents.yaml`) and skill registry (`catalog/registry/skills.yaml`).
- Agent descriptors in `catalog/agents/{main,sub}/<agent-slug>/agent.yaml`.
- JSON Schema contracts in `catalog/contracts/` consumed by agents and skills.
- CI workflows executing governance checks and packaging validation.

## MAG/SAG Roadmap

### Completed (v0.1.0)
- [x] Agent Runner with MAG/SAG invocation and observability
- [x] Registry loader for agent/skill resolution
- [x] OfferOrchestratorMAG (main agent) and CompensationAdvisorSAG (sub-agent)
- [x] CLI command `agdd agent run` for MAG execution
- [x] Contracts: candidate_profile, comp_advisor_input/output, offer_packet
- [x] Skills: salary-band-lookup, task-decomposition, result-aggregation
- [x] E2E integration tests with observability validation

### Short-Term (v0.2.0)
- [ ] Additional SAG variants (data-analysis-sag, document-processing-sag)
- [ ] Async/parallel SAG invocation for MAGs
- [ ] A/B testing support in registry (variant selection by score)
- [ ] Enhanced observability dashboard (visualize MAG→SAG flows)

### Medium-Term (v0.3.0)
- [ ] MCP integration for SAG skills (enhanced data access)
- [ ] Governance policies for agent execution (SLO enforcement)
- [ ] Agent health monitoring and circuit breaker patterns
- [ ] Distributed tracing across MAG→SAG boundaries

### Long-Term
- [ ] Multi-MAG orchestration (MAG calling other MAGs)
- [ ] Dynamic SAG selection based on runtime conditions
- [ ] Agent versioning and blue/green deployments
- [ ] Cost optimization and budget management per agent

---
**Created**: 2025-10-20 02:27 UTC
**Last Updated**: 2025-10-21 (MAG/SAG implementation)
