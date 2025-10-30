---
title: AGDD ExecPlan Registry
slug: plans
status: living
last_synced: 2025-10-30
tags: [agdd, execplan, roadmap, workflow]
description: "Execution-plan convention for coordinating multi-session initiatives across the AG-Driven Development framework."
source_of_truth: "https://github.com/artificial-intelligence-first/agdd"
sources:
  - { id: R1, title: "OpenAI Cookbook – Exec Plans", url: "https://cookbook.openai.com/articles/codex_exec_plans", accessed: "2025-10-30" }
  - { id: R2, title: "AGDD Roadmap", url: "../development/roadmap.md", accessed: "2025-10-30" }
  - { id: R3, title: "Single Source of Truth", url: "./ssot.md", accessed: "2025-10-30" }
---

# AGDD ExecPlans (PLANS.md)

> **For Humans**: ExecPlans turn complex work into resumable, auditable tasks. Use this document to structure plans and keep the roadmap current.
>
> **For AI Agents**: Do not start multi-session or high-risk work without an ExecPlan. Update timestamps, decisions, and discoveries in real time so another contributor can resume safely.

## Purpose

ExecPlans capture the intent, steps, and validation for initiatives such as:

- New MAG/SAG agent families or major skill migrations
- Storage backend changes (SQLite → Postgres, enabling Redis cache, etc.)
- Governance or routing overhauls across multiple catalog assets
- Framework releases involving CLI, API, documentation, and observability updates
- Incident investigations that span discovery → mitigation → retro

## Canonical Structure

Create each plan under `docs/development/plans/<kebab-slug>.md` using the structure below:

```markdown
# <Action-oriented title>

## Purpose / Big Picture
- Why the work matters and success criteria.

## Context and Orientation
- Links to issues, SSOT entries, catalog files, diagrams.

## Plan of Work
- Phases, dependencies, risk notes.

## To-do
- [ ] Checklist grouped by phase/owner.

## Progress
- [YYYY-MM-DD HH:MM UTC] Timestamped updates.

## Decision Log
- [YYYY-MM-DD HH:MM UTC] Decision with rationale and alternatives.

## Surprises & Discoveries
- [YYYY-MM-DD HH:MM UTC] Unexpected findings, blockers, coping strategies.

## Concrete Steps
- Ordered implementation notes and commands.

## Validation and Acceptance
- Tests, scripts, manual checks and expected outputs.

## Idempotence and Recovery
- Rollback instructions, backup locations, how to retry safely.

## Outcomes & Retrospective
- Final state, follow-ups, lessons learned.

## Artifacts and Notes
- PRs, run IDs, dashboards, documents.

## Interfaces and Dependencies
- Services, APIs, schemas, or teams impacted.
```

## Workflow

1. **Initiate**: Draft the file, link it in the “Active Plans” list, and tag owners.
2. **Operate**: Update To-do, Progress, Decision Log, and Surprises sections as work advances. Use UTC timestamps.
3. **Validate**: Record the exact commands executed (pytest, mypy, agdd flow gate, storage migrations) with outcomes.
4. **Close**: Complete To-do boxes, fill Outcomes & Retrospective, move entry to “Completed Plans,” and note follow-up tasks.
5. **Cross-link**: Reference the plan in `CHANGELOG.md`, `SSOT.md`, or relevant docs when definitions or behaviour change.

## Active Plans

_None. Add entries in the format below when initiatives start._

```markdown
- [YYYY-MM-DD] Title – Link – Owner(s) – Status (in-progress/blocking/paused)
```

## Completed Plans

- [2025-10-15] `bootstrap-initial-agdd-release.md` – Initial release packaging and documentation alignment.

## Best Practices

- Keep language actionable and concise.
- Prefer small, linked plans over monolithic documents.
- Store supporting assets (diagrams, SQL snippets, scripts) next to the plan or in `docs/assets/`.
- When coordination spans multiple teams, name responsible owners in the plan header.

## Example Snippets

### Storage Migration Checklist
```markdown
## Validation and Acceptance
- [ ] `uv run agdd data init --backend postgres`
- [ ] `uv run -m pytest tests/storage/test_postgres_backend.py`
- [ ] Manual smoke test for `uv run agdd data vacuum --dry-run`
```

### Incident Log Entry
```markdown
## Surprises & Discoveries
- [2025-10-30 11:42 UTC] Flow Runner returned 403 because `AGDD_API_KEY` rotated without redeploy. Added key refresh to plan.
```

## Update Log

- 2025-10-30: Established AGDD ExecPlan registry and workflow overview.
