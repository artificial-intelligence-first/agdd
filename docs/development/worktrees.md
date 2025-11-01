# Git Worktree Operations

MAGSAG provisions one Git worktree per agent run to isolate file changes and reduce merge conflicts. The implementation introduced in `feat/git-worktree` surfaces consistent tooling across the CLI, API, and observability stack.

## Directory Layout

- Worktrees live outside the main checkout at `../.worktrees/` (override with `MAGSAG_WORKTREES_ROOT`).
- Each tree is created inside `wt-<runId>-<task>-<shortSHA>` and checks out branch `wt/<runId>/<task>` unless `--detach` is used.
- The metadata file `.magsag-worktree.json` persists run metadata and is removed automatically during `git worktree remove`.

## Environment Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `MAGSAG_WORKTREES_ROOT` | `../.worktrees` | Location where managed worktrees are created. |
| `MAGSAG_WT_MAX_CONCURRENCY` | `8` | Maximum number of active managed worktrees. |
| `MAGSAG_WT_TTL` | `14d` | Default expiry horizon passed to `git worktree prune`. |
| `MAGSAG_WT_ALLOW_FORCE` | unset | Set to `1`/`true` in CI maintenance jobs to allow forced removals. |

Protected bases (`main`, `release/*`) and `--force` removals are guarded by policy.

## CLI Usage

```
uv run magsag wt new <runId> --task <slug> --base <branch|sha> [--detach] [--no-checkout] [--lock] [--lock-reason]
uv run magsag wt ls [--json]
uv run magsag wt rm <runId> [--force]
uv run magsag wt lock <runId> [--reason]
uv run magsag wt unlock <runId>
uv run magsag wt gc [--expire <duration>]
uv run magsag wt repair
```

The CLI surfaces structured errors for conflicts, dirty trees, or policy violations.
`magsag wt rm` automatically runs `git worktree prune --expire=<MAGSAG_WT_TTL>` to garbage-collect
stale administrative entries after a successful removal.

## HTTP API

| Method | Path | Description | Scopes |
| --- | --- | --- | --- |
| `GET` | `/api/v1/worktrees` | List managed worktrees. | `worktrees:read` |
| `POST` | `/api/v1/worktrees` | Create a worktree (`lock`, `lock_reason`, `detach`, `no_checkout`). | `worktrees:write` |
| `DELETE` | `/api/v1/worktrees/{id}` | Remove by run ID or directory name (`force` query flag). | `worktrees:write` |
| `POST` | `/api/v1/worktrees/{id}/lock` | Lock the worktree. | `worktrees:lock` |
| `POST` | `/api/v1/worktrees/{id}/unlock` | Unlock the worktree. | `worktrees:unlock` |
| `POST` | `/api/v1/worktrees/gc` | Run `git worktree prune`. | `worktrees:maintain` |
| `POST` | `/api/v1/worktrees/repair` | Run `git worktree repair`. | `worktrees:maintain` |
| `GET` | `/api/v1/worktrees/events` | Server-sent events (`worktree.create/remove/lock/unlock/prune/repair`). | `worktrees:read` |

Responses are serialized with `WorktreeResponse`, exposing run metadata, lock state, prunable flags, and timestamps.

## Observability

Operations emit OpenTelemetry spans (`git.worktree.add`, `git.worktree.list`, `git.worktree.remove`, `git.worktree.prune`, `git.worktree.lock`, `git.worktree.unlock`, `git.worktree.repair`) and Langfuse metrics when enabled:

- Histogram `worktree_create_duration_ms`
- Histogram `worktree_remove_duration_ms`
- UpDownCounter `worktrees_active`

Events flow through an in-process bus; subscribers register via `get_event_bus().register()` and receive `WorktreeEvent` items published by the manager and CLI/API surfaces.

## Testing Notes

Unit tests validate porcelain parsing, branch naming guards, and cleanup behaviour. Integration tests exercise `WorktreeManager` end-to-end using a temporary repository, including event emission, locking, and removal.
