# AGDD Git Worktree Adoption Plan

## Purpose and Guiding Principles
- Objective: Run each AI task in an isolated Git worktree with a dedicated branch so concurrent development has near-zero conflicts or context switching.
- 1 worktree = 1 branch; never check out the same branch in multiple worktrees. Avoid `--force` except for the CI maintenance role.
- Place worktrees outside the repository root (default `../.worktrees/<run>`), mirroring official Git guidance.
- Expose machine-parseable state via `git worktree list --porcelain -z`.
- Protect long-lived or approval-waiting jobs with `git worktree lock`/`unlock`.
- Remove worktrees only when clean; pair `remove` with `prune --expire` for automation.

## Physical Layout and Naming
- Worktree root: `${REPO}/../.worktrees/`.
- Directory pattern: `../.worktrees/wt-<runId>-<task>-<shortSHA>`.
- Branch pattern: `wt/<runId>/<task>` to keep branches unique, ephemeral, and traceable.
- Ensure `/.worktrees/` is ignored in the primary checkout to prevent accidental staging.

## Operations Design
- Create from existing branch: `git worktree add ../.worktrees/<dir> <branch>` when the branch is unused elsewhere.
- Create with new branch: `git worktree add -b wt/<runId>/<task> ../.worktrees/<dir> <base>`.
- Detached experimentation: `git worktree add --detach ../.worktrees/<dir> <commit-ish>`.
- Deferred checkout: `git worktree add --no-checkout ...` for sparse operations.
- Inventory: `git worktree list --porcelain -z` parsed into structured data.
- Locking: `git worktree lock --reason "<text>"` / `git worktree unlock <path>` to protect pending work.
- Removal: `git worktree remove <path>` (clean trees only; `--force` permitted solely for CI maintenance).
- Garbage collection: `git worktree prune --expire=<duration>` to clean orphan metadata.
- Recovery: `git worktree repair` restores broken directory references.
- Optional remote inference: use `--guess-remote` or configure `checkout.defaultRemote=origin`.

## Integration into AGDD (CLI, API, Events)
- Typer CLI (`agdd wt`):
  - `agdd wt new <runId> --task <slug> --base <branch|sha> [--detach] [--no-checkout] [--lock]`.
  - `agdd wt ls [--json]` returning parsed worktree metadata.
  - `agdd wt rm <runId> [--force]` with clean-tree enforcement and CI-only force.
  - `agdd wt gc [--expire <duration>]`.
  - `agdd wt lock <runId> [--reason]` / `agdd wt unlock <runId>`.
  - Emit `worktree.*` events to the existing event bus.
- FastAPI:
  - `POST /api/v1/worktrees` to create.
  - `GET /api/v1/worktrees` to list.
  - `DELETE /api/v1/worktrees/{id}` with optional `force=false`.
  - SSE stream gains `worktree.create/remove/lock/unlock/prune/repair`.
- Governance:
  - Disallow worktree creation from `main` and `release/*`.
  - Gate `--force` removal behind CI maintenance role checks.
  - Normalize user-supplied paths to prevent escaping `WORKTREES_ROOT`.

## Parallel Execution Policy
- Guarantee 1 task ↔ 1 worktree ↔ 1 ephemeral branch.
- Enforce `AGDD_WT_MAX_CONCURRENCY` (default 8) by counting existing worktrees before creation; reject beyond limit.
- Apply TTL via `AGDD_WT_TTL` (default 14 days); expired entries are pruned during `gc`.
- Approval-gated tasks lock the worktree until explicit unlock after gate completion.

## CI/CD Operations
- Workflow: runners execute `git fetch --all --prune --tags` then `agdd wt new ...`.
- Branch lifecycle: branch `wt/<runId>/<task>` pushed to `origin` for PR automation; remove worktree and prune after merge.
- Scheduled cleanup: nightly `agdd wt gc --expire "3.days.ago"` (cross-platform cron/Task Scheduler coverage).

## Failure Modes and Recovery
- Removal blocked by dirty tree: surface actionable error; instruct commit/stash; allow CI-maintainer `--force` as last resort.
- Directory relocation: run `git worktree repair` to relink metadata.
- Duplicate checkout attempts: rely on Git refusal; fallback to detached or new branch strategies.

## Observability and Metrics
- OpenTelemetry spans named `git.worktree.{add|list|remove|prune|lock|unlock}` enriched with `worktree_id`, `branch`, `path`, `locked`.
- Langfuse metrics: `worktree_create_duration_ms`, `worktree_remove_duration_ms`, `worktrees_active`.
- Include cost, duration, and success counters for concurrency dashboards.

## Copy-Ready Agent Prompt
```
Role: Git Worktree rollout implementer for the AGDD repository.
Goal: Integrate a resilient, reproducible, high-throughput worktree workflow into AGDD v0.2.
Acceptance Criteria:
- Provide `agdd wt` CLI and FastAPI endpoints covering new/ls/rm/gc/lock/unlock.
- Default worktrees to `../.worktrees/` and prevent conflicting checkouts.
- Enforce 1 worktree = 1 ephemeral branch (`wt/<runId>/<task>`).
- Parse `git worktree list --porcelain -z` for listings.
- Require clean trees for remove; allow `--force` only for CI.
- Support lock/unlock/prune/repair across CLI/API/SSE.
- Emit OTel/Langfuse telemetry for worktree lifecycle.
- Honor `AGDD_WT_MAX_CONCURRENCY` and `AGDD_WT_TTL`.
- Deliver docs, samples, CI hooks; keep mypy, ruff, pytest green.
Branch: `feat/git-worktree`.
```

## Tests
- Unit: porcelain parser, branch/worktree collision checks, forced removal guard, concurrency enforcement.
- Integration: create→commit→remove flow, detached and no-checkout variants, lock/unlock cycle, prune/repair.
- All tests must complete within 30 seconds; ensure `mypy`, `ruff`, and `pytest` remain green.

## Safety Notes
- Follow Git official semantics for `add`, `list`, `lock`, `remove`, `prune`, `repair`, including `--detach` and `--no-checkout`.
- Respect Git’s default refusal to checkout identical branches across multiple worktrees.
- Use `--force` only when absolutely necessary and only inside CI maintenance contexts.
