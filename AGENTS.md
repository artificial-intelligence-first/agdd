---
title: AGDD Agents Playbook
slug: agents
status: living
last_updated: 2025-10-30
tags: [agdd, agents, automation, governance]
summary: "Machine-oriented operating manual for contributors and AI assistants working inside the AG-Driven Development framework."
sources:
  - { id: R1, title: "AGDD README", url: "README.md", accessed: "2025-10-30" }
  - { id: R2, title: "Agent Runner Implementation", url: "src/agdd/runners/agent_runner.py", accessed: "2025-10-30" }
  - { id: R3, title: "Single Source of Truth", url: "SSOT.md", accessed: "2025-10-30" }
---

# AGDD Agents Playbook (AGENTS.md)

> **For Humans**: This document captures the canonical workflow AI assistants follow when touching the AGDD repository. Use it to understand which commands they run, how they validate work, and where they record changes.
>
> **For AI Agents**: Obey every instruction in this playbook unless the user overrides it explicitly. When in doubt, stop and ask instead of guessing.

## Dev Environment Tips

- **Language & Runtime**: Python 3.12+. Use [`uv`](https://docs.astral.sh/uv/) for dependency management (`uv sync --extra dev`).
- **Project layout**: Source lives under `src/agdd/`, catalog assets under `catalog/`, integration docs in `docs/`.
- **CLI entry point**: `uv run agdd --help` for Typer-based commands (`flow`, `agent`, `data`, `mcp`).
- **API server**: `uv run uvicorn agdd.api.server:app --reload` for local development.
- **Environment variables**: All runtime configuration uses the `AGDD_` prefix. See `agdd.api.config.Settings` for defaults.
- **Storage**: SQLite lives at `.agdd/storage.db`. Postgres and Redis extras activate when installed via `uv sync --extra production`.
- **Observability artifacts**: Agent execution writes JSONL logs, metrics, and run summaries under `.runs/agents/<run-id>/`.

## Testing Instructions

- One-time setup for development tools (enables parallel tests):
  ```bash
  uv sync --extra dev
  ```

- Run the fast suite before committing (default excludes slow, parallel on):
  ```bash
  uv run --no-sync -m pytest -q
  ```
- Execute slow or integration targets when touching runners, MCP, or catalog flows:
  ```bash
  uv run --no-sync -m pytest -m slow
  uv run --no-sync -m pytest tests/integration/test_e2e_offer_flow.py
  ```
- Run MCP-focused tests with the full suite enabled:
  ```bash
  make test-mcp
  ```

- Make shortcuts:
  ```bash
  make test        # fast suite (default, excludes slow)
  make test-all    # fast + slow
  make test-slow   # slow only
  ```
- Type checking is mandatory:
  ```bash
  uv run mypy src tests
  ```
- Linting and formatting:
  ```bash
  uv run ruff format .
  uv run ruff check .
  ```
- Validate catalog schemas via pytest (covered in test suite)
- Flow Runner governance checks:
  ```bash
  uv run agdd flow validate examples/flowrunner/prompt_flow.yaml
  uv run agdd flow gate path/to/summary.json
  ```
- Record test results in your message; never claim success without running the commands above unless the user explicitly waives them.

## Build & Deployment

- Package build: `uv build` (setuptools backend).
- API launch (production-style): `uv run uvicorn agdd.api.server:app --host 0.0.0.0 --port 8000`.
- Storage lifecycle: `uv run agdd data init`, `uv run agdd data vacuum --dry-run`, `uv run agdd data vacuum`.
- MCP server: `uv run agdd mcp serve` exposes registered agents and skills to Model Context Protocol clients.
- Always document deployment steps in the relevant ExecPlan and note outcomes in `docs/development/changelog.md`.

## Linting & Code Quality

- Respect the 100-character line limit configured in `pyproject.toml`.
- Use docstrings for public APIs and include type hints everywhere.
- Run `uv run bandit -r src` when touching security-sensitive code.
- Keep dependencies pinned through `pyproject.toml` + `uv.lock`; do not edit `requirements.txt` (not used).

## PR Instructions

1. Create a branch: `feature/<slug>` or `fix/<issue-id>`.
2. Implement changes with accompanying tests and docs.
3. Update documentation: `README.md`, `SSOT.md`, `SKILL.md`, and relevant guides under `docs/`.
4. Update `CHANGELOG.md` (`## [Unreleased]`).
5. Prepare PR description including:
   - Summary of changes and impacted components.
   - Commands executed with pass/fail outcome.
   - Follow-up work, migration steps, or rollout concerns.
6. Keep commits clean (rebase preferred). CI must be green before requesting review.

## Security & Credentials

- Never commit secrets or tokens. Use environment variables and secret managers.
- Sanitize logs that might include user data or model outputs flagged by moderation.
- Follow `SECURITY.md` for vulnerability disclosure and incident handling.
- When storing artefacts externally, ensure the destination is approved and documented in `SSOT.md`.

## Observability & Governance

- Use `ObservabilityLogger` for new agent stages; ensure start/end events and placeholder cost metrics are recorded.
- Update governance policies under `catalog/policies/` when creating new quality gates.
- Summaries produced by Flow Runner must pass `agdd flow gate` before merging automation changes.

## ExecPlan Workflow

- Create ExecPlans for multi-session or high-risk work. Store them under `docs/development/plans/` and register them in `PLANS.md`.
- Update Progress, Decision Log, and Surprises/Discoveries sections in real time with UTC timestamps.
- Close plans by documenting outcomes, validation evidence, and follow-up tasks.

## Reference Surfaces

- **Canonical terminology**: `SSOT.md`.
- **Agent orchestration**: `src/agdd/runners/agent_runner.py`.
- **Skill runtime**: `catalog/registry/skills.yaml`, `catalog/skills/*/` directories.
- **Governance configuration**: `catalog/policies/`, `catalog/routing/`.
- **Integration guides**: `docs/guides/` (MCP integration, cost optimisation, semantic cache, etc.).

## When to Pause and Ask

- Requirements conflict with `SSOT.md` or governance policies.
- User requests destructive actions (e.g., rewriting history, deleting data) without explicit approval.
- Test commands fail or produce ambiguous output.
- MCP servers or external dependencies are unavailable and no fallback exists.

## Update Log

- 2025-10-30: Rebuilt AGENTS.md to follow SSOT convention with AGDD-specific workflows.
