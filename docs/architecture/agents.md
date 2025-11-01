---
title: MAGSAG Agent Guidelines
slug: agents
status: living
last_synced: 2025-10-30
tags: [magsag, agents, workflow]
description: "Concise operating rules for developers and AI assistants working on MAGSAG."
source_of_truth: "https://github.com/artificial-intelligence-first/magsag"
---

# MAGSAG Agent Guidelines

The goal of this playbook is to keep human and AI contributors aligned on the
minimum set of rules required to land safe changes quickly. Everything here is
actionable; follow it unless the user or maintainer explicitly overrides it.

## Environment Essentials

- Use Python 3.12 with [`uv`](https://docs.astral.sh/uv/) for dependency
  management: `uv sync --extra dev`.
- Source code lives under `src/magsag/`, catalog assets under `catalog/`, docs in
  `docs/`. Keep new modules inside `src/magsag/` unless instructed otherwise.
- The Typer CLI is the primary entry point: `uv run magsag --help`.
- Run the API server locally with `uv run python -m magsag.api.server`.
- Configuration is namespaced by `MAGSAG_`; defaults are in
  `magsag.api.config.Settings`.

## Architecture Snapshot

```
┌──────────────────────────────────────────────────────────────┐
│                          Interfaces                          │
│   Typer CLI (wt/agent/flow)  FastAPI API  GitHub Hooks & Jobs │
└───────────────┬────────────────────┬──────────────────────────┘
                │                    │
                ▼                    ▼
┌──────────────────────────────────────────────────────────────┐
│                 Orchestration & Governance                    │
│   Runner Hooks ─ Approvals ─ Policies ─ Worktree Manager     │
│   Agent Runner ─ Skill Runtime ─ Flow Runner adapters        │
└──────────────────────────┬────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                 Execution & Observability                     │
│   Catalog (agents/skills/contracts)                           │
│   Storage (SQLite, Postgres) + MCP Providers                   │
│   Telemetry (OpenTelemetry, Langfuse)                          │
└──────────────────────────────────────────────────────────────┘
```

- Interfaces feed the orchestration layer.
- Governance enforces approvals and emits audit events.
- Catalog assets, storage backends, and MCP providers execute the work.

## Repository Layout

```
src/magsag/          → Core package code (api, runners, worktree, governance, observability)
catalog/             → Agents, skills, schemas, policies
docs/                → Architecture notes, guides, development docs
ops/                 → Maintenance scripts and tooling
benchmarks/          → Performance harnesses
tests/               → Unit, integration, observability, MCP suites
```

## Required Checks Before Any PR

```bash
uv run ruff check
uv run mypy src/magsag tests
uv run pytest -q -m "not slow"
uv run python ops/tools/check_docs.py
```

If a check is intentionally skipped, state the reason in the delivery message.

## Change Workflow

1. Create an isolated worktree: `uv run magsag wt new <run> --task <slug> --base main`.
2. Implement the change with type hints and focused tests.
3. Update documentation or catalog entries impacted by the change.
4. Record the commands you executed and their outcomes.
5. Stage changes with `git add -u` (rename-aware) and avoid unrelated drive-by edits.

## Governance Expectations

- Never commit secrets. Use environment variables or the secret manager referenced
  in `docs/policies/security.md`.
- Keep naming consistent with the `magsag` package. Do not reintroduce legacy `agdd`
  tokens or directories.
- Update `CHANGELOG.md` under `## [Unreleased]` whenever public behaviour or docs shift.
- Prefer incremental plans (`docs/development/plans/`) for multi-session work and
  close them with validation notes once delivered.

## When to Pause and Ask

- Requirements conflict with `docs/architecture/ssot.md`.
- A destructive action is requested without explicit approval (e.g., rewriting git
  history, purging data).
- External dependencies (OpenAI, Anthropic, Flow Runner) fail and no fallback
  exists.
- Governance policies or security guidelines seem ambiguous.

## Reference Surfaces

- `src/magsag/runners/agent_runner.py` – canonical executor.
- `catalog/registry/` – agent and skill registry entries.
- `docs/guides/` – integration-specific walkthroughs (MCP, moderation, GitHub).
- `docs/development/worktrees.md` – detailed worktree automation.

Keep this file concise. If you need deep details, link out to the dedicated guide
instead of inlining them here.
