---
title: Contributing to AGDD
slug: contributing
status: living
last_updated: 2025-10-30
tags: [agdd, contributing, governance, collaboration]
summary: "Guidelines for contributing to the AG-Driven Development framework and keeping documentation, tests, and governance in sync."
sources:
  - { id: R1, title: "AGDD README", url: "README.md", accessed: "2025-10-30" }
  - { id: R2, title: "Agent Development Guide", url: "docs/guides/agent-development.md", accessed: "2025-10-30" }
  - { id: R3, title: "Single Source of Truth", url: "SSOT.md", accessed: "2025-10-30" }
---

# Contributing to AGDD

> **For Humans**: Thank you for improving AGDD. This guide explains our expectations, branching model, and validation steps so your work lands smoothly.
>
> **For AI Agents**: Follow every checklist exactly. Keep AGENTS.md and SSOT.md in sync, document changes, and never skip validations unless the user waives them.

## Project Values

- **Governance-first**: Every change must respect policies defined in `catalog/policies/` and the contracts recorded in `SSOT.md`.
- **Observable**: Record results in `.runs/`, update `CHANGELOG.md`, and cross-link ExecPlans so work stays traceable.
- **Safe automation**: Prefer minimal diffs, avoid destructive commands, and halt when requirements conflict with repository policies.

## Before You Start

1. Read `README.md`, `SSOT.md`, and `AGENTS.md` to understand current capabilities and workflow expectations.
2. Sync dependencies: `uv sync --extra dev` (add `--extra production` when working with Postgres/Redis/MCP).
3. Verify local environment by running:
   ```bash
   uv run -m pytest -q
   uv run mypy src tests
   uv run ruff check .
   ```
4. Confirm feature alignment against `docs/development/roadmap.md` and open issues.

## Issue Workflow

- **Bug reports**: Include reproduction steps, expected vs. actual behaviour, logs from `.runs/agents/<run-id>/`, and environment information.
- **Feature requests**: Provide problem statement, proposed solution, acceptance criteria, and references to affected agents/skills.
- **Design discussions**: Use GitHub discussions or link design docs under `docs/development/`. Capture outcomes in an ExecPlan if work spans multiple sessions.

## Development Process

1. Branch from `main` (`feature/<slug>` or `fix/<issue>`).
2. Write or update ExecPlan entries (see `PLANS.md`) when work is multi-phase.
3. Implement changes with strict type hints and tests.
4. Update documentation:
   - `README.md` for user-facing capabilities.
   - `AGENTS.md` for operational changes.
   - `SKILL.md` when modifying skill conventions.
   - `SSOT.md` for new terminology, schemas, or policies.
5. Run validation commands (tests, lint, type check, schema validators).
6. Update `CHANGELOG.md` under `## [Unreleased]` with user-facing changes.
7. Commit using imperative, Conventional Commit-friendly summaries (≤72 chars).
8. Push and open a pull request with:
   - Summary of changes and touched components.
   - Testing evidence (commands + results).
   - Rollout or migration notes.
   - Links to updated ExecPlans or docs.

## Testing & Quality Gates

| Command | Purpose |
|---------|---------|
| `uv run -m pytest -q` | Fast test suite (excludes `slow`). |
| `uv run -m pytest -m slow` | Slow/integration scenarios (run when affecting flows, MCP, or storage). |
| `uv run mypy src tests` | Strict type checking. |
| `uv run ruff format .` | Auto-format. |
| `uv run ruff check .` | Lint enforcement. |
| `uv run bandit -r src` | Security scanning for Python code. |
| `uv run python ops/tools/validate_catalog.py` | Validate catalog YAML + JSON Schemas. |
| `uv run agdd flow validate <flow>` | Ensure Flow Runner configs remain valid. |
| `uv run agdd flow gate <summary.json>` | Apply governance thresholds to flow summaries. |

Record pass/fail results for each command in the PR description.

## Documentation Standards

- Keep docs concise and actionable. Avoid rhetorical language.
- Update diagrams, examples, and CLI excerpts when behaviour changes.
- Maintain Update Log sections at the bottom of AGENTS.md, SKILL.md, SSOT.md, PLANS.md, and similar files.
- Ensure cross-references remain accurate (e.g., README → docs/guides, SSOT definitions → catalog files).

## Review & Merge

- CI must pass (`pytest`, `ruff`, `mypy`, doc checks) before requesting review.
- Reviewers focus on correctness, tests, docs, and governance compliance.
- Address feedback promptly; prefer rebasing over merge commits.
- Squash or rebase before merge. Tag releases only after maintainers update `CHANGELOG.md` and confirm readiness.

## Security & Responsible Disclosure

- Follow `SECURITY.md` for reporting vulnerabilities.
- Do not expose secrets or PII in tests or documentation.
- Coordinate with maintainers before publishing any security-related changes.

## Support Channels

- **Issues**: https://github.com/artificial-intelligence-first/agdd/issues
- **Docs**: `docs/guides/` for deep dives (agent dev, API usage, MCP integration, semantic cache, moderation, cost optimisation).
- **Roadmap**: `docs/development/roadmap.md`
- **Changelog**: `CHANGELOG.md` and `docs/development/changelog.md`

## Update Log

- 2025-10-30: Rebuilt CONTRIBUTING guide with governance, validation, and documentation requirements aligned to AGDD.
