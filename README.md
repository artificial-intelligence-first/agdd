# MAGSAG Framework

**This repository has been migrated to [artificial-intelligence-first/magsag](https://github.com/artificial-intelligence-first/magsag). Please use the new repository for all updates, issues, and pull requests.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![CI Status](https://img.shields.io/github/actions/workflow/status/artificial-intelligence-first/magsag/ci.yml?branch=main&label=CI)](https://github.com/artificial-intelligence-first/magsag/actions/workflows/ci.yml?branch=main)

MAGSAG is a governance-first framework for building and operating AI agent workflows.
It provides a single runtime that spans CLI tools, FastAPI endpoints, GitHub
automation, and observability features backed by OpenTelemetry and Langfuse.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                          Interfaces                          │
│   ┌───────────────┐    ┌───────────────┐    ┌──────────────┐ │
│   │  Typer CLI    │    │  FastAPI API  │    │ GitHub Hooks │ │
│   │ (magsag wt/…) │    │ (/api/v1/…)   │    │  & Jobs      │ │
│   └──────┬────────┘    └──────┬────────┘    └──────┬───────┘ │
└──────────┼────────────────────┼────────────────────┼─────────┘
           │                    │                    │
           ▼                    ▼                    ▼
┌──────────────────────────────────────────────────────────────┐
│                     Orchestration Layer                      │
│   ┌──────────────────────────────────────────────────────┐   │
│   │  Runner Hooks & Governance (approvals, policies)     │   │
│   │  Worktree Manager (git worktree lifecycle)           │   │
│   │  Agent Runner (MAG/SAG coordination, skills runtime) │   │
│   └──────────────────────────────┬───────────────────────┘   │
└──────────────────────────────────┼───────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────┐
│                    Execution & Observability                 │
│   ┌──────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│   │ Catalog  │   │ Storage APIs │   │  Telemetry (OTel,    │ │
│   │ (agents, │   │ (SQLite,     │   │  Langfuse)           │ │
│   │ skills,  │   └──────┬───────┘   └───────────┬──────────┘ │
│   │ schemas) │          │                       │            │
│   └─────┬────┘          │                       │            │
│         │        ┌──────▼──────────┐    ┌───────▼──────────┐ │
│         └──────▶ │ Providers &     │    │  Event Storage   │ │
│                  │ MCP Integrations│    │  (append_event)  │ │
│                  └─────────────────┘    └──────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

- Interfaces (CLI, API, GitHub) trigger orchestration components.
- Runner hooks enforce approvals and emit audit/telemetry events.
- Catalog, storage backends, and providers back the execution layer.

### Repository Layout

```
.
├── src/magsag/                # Package code: API, CLI, runners, governance
│   ├── api/                   # FastAPI app, routes, config
│   ├── runners/               # MAG/SAG orchestration and Flow Runner bridge
│   ├── worktree/              # Git worktree lifecycle management
│   ├── governance/            # Approvals, policies, permission evaluation
│   ├── observability/         # Logging, tracing, cost tracking
│   └── ...                    # MCP, moderation, storage, optimization, etc.
├── catalog/                   # Agents, skills, JSON Schema contracts, policies
├── docs/                      # Architecture notes, guides, development docs
├── ops/                       # Maintenance scripts and automated tooling
├── benchmarks/                # Performance harnesses
└── tests/                     # Unit, integration, observability, MCP suites
```

---

## Getting Started

```bash
# 1. Install dependencies (creates .venv/)
uv sync --extra dev

# 2. Inspect available commands
uv run magsag --help

# 3. Start the FastAPI server (Ctrl+C to stop)
uv run python -m magsag.api.server
```

The default configuration runs completely locally. Environment variables prefixed
with `MAGSAG_` enable optional integrations (OpenAI, Anthropic, GitHub, Langfuse,
etc.). See `docs/development/contributing.md` for a full configuration matrix.

---

## Common Tasks

### Validation & Quality Gates

```bash
# Static checks
uv run ruff check
uv run mypy src/magsag tests

# Test suite (parallel, skips slow fixtures)
uv run pytest -q -m "not slow"

# Documentation guard
uv run python ops/tools/check_docs.py
```

### CLI Highlights

```bash
# Git worktree lifecycle (new/list/remove/lock/unlock/gc/repair)
uv run magsag wt --help

# Agent orchestration (run agents, inspect metadata)
uv run magsag agent --help

# Flow Runner integration (requires flow-runner checkout)
uv run magsag flow --help
```

### Worktree Workflow (Recommended)

1. Create an isolated branch/worktree:
   ```bash
   uv run magsag wt new run-123 --task docs-refresh --base main
   ```
2. Lock a long-running job while waiting for approval:
   ```bash
   uv run magsag wt lock run-123 --reason "awaiting review"
   ```
3. Clean up when finished:
   ```bash
   uv run magsag wt rm run-123
   ```

For automation examples see `docs/development/worktrees.md`.

---

## Documentation Map

- `docs/architecture/` – system design, governance model, and telemetry layers
- `docs/guides/` – task-focused walkthroughs (API usage, moderation, MCP, etc.)
- `docs/development/` – local development workflow, roadmap, changelog
- `catalog/` – reference agents, skills, and JSON Schema contracts used in tests

Each document has been trimmed to focus on actionable guidance. When in doubt,
start with `docs/architecture/agents.md` for a high-level picture and branch out
to the relevant guide.

---

## Contributing

- Use `magsag wt` to keep branches isolated and reproducible.
- Run the validation suite (`ruff`, `mypy`, `pytest`, `check_docs`) before sending
a pull request.
- Keep naming aligned with the `magsag` package and `MAGSAG_` environment prefixes.

See `CONTRIBUTING.md` for review conventions and release automation.

---

## License

MAGSAG is released under the [MIT License](./LICENSE).
