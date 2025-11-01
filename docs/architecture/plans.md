---
title: ExecPlan Quick Reference
slug: plans
status: living
last_synced: 2025-10-30
tags: [magsag, execplan]
description: "How to create, maintain, and close ExecPlans without unnecessary overhead."
source_of_truth: "https://github.com/artificial-intelligence-first/magsag"
---

# ExecPlan Quick Reference

ExecPlans are lightweight documents that capture intent, validation, and
handoff notes for work that spans multiple sessions or contributors. Keep them
short, link to relevant assets, and update them while you work.

## When to Create One

- Feature work that spans CLI, API, and catalog changes.
- Infrastructure migrations (storage engines, observability backends).
- Governance or policy changes that affect more than one surface.
- Incident response efforts that require traceable decisions.

## Minimal Template

Store plans in `docs/development/plans/<slug>.md` and follow this structure:

```markdown
# <Action title>

## Purpose
- Why this is needed, success in one sentence.

## Context
- Links to issues, SSOT entries, diagrams, docs.

## Plan of Work
1. Ordered steps with owners.
2. Risks or dependencies.

## Validation
- Commands with expected outcomes.
- Rollback or recovery notes if something fails.

## Status
- [YYYY-MM-DD HH:MM UTC] Progress updates.
- Decision log with rationale.

## Follow-up
- Remaining tasks or references (PRs, dashboards).
```

## Workflow Checklist

1. Draft the file and add it to the “Active Plans” list in `PLANS.md`.
2. Update the `Status` and `Decision` sections in real time using UTC.
3. Record the exact validation commands you ran, including failures.
4. Close the plan once the work ships (checklist complete, outcomes noted).
5. Move the entry to “Completed Plans” and cross-link changelog or docs.

## Best Practices

- Keep language direct; use links instead of lengthy quotes.
- Prefer multiple small plans over one bloated document.
- Attach supporting scripts or diagrams next to the plan under the same slug.
- Reflect key learnings in `docs/architecture/ssot.md` or other canonical surfaces.

That’s all—ExecPlans should guide action, not become another maintenance burden.
