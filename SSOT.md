---
title: AGDD Single Source of Truth
slug: ssot
status: living
last_updated: 2025-10-30
tags: [agdd, ssot, governance, contracts, terminology]
summary: "Canonical definitions, data contracts, policies, and interfaces for the AG-Driven Development framework."
sources:
  - { id: R1, title: "AGDD Catalog", url: "catalog/", accessed: "2025-10-30" }
  - { id: R2, title: "AGDD API Server", url: "src/agdd/api/server.py", accessed: "2025-10-30" }
  - { id: R3, title: "Observability Logger", url: "src/agdd/observability/logger.py", accessed: "2025-10-30" }
---

# AGDD Single Source of Truth (SSOT)

> **For Humans**: Treat this file as authoritative. Update it before changing terminology, contracts, or governance policies, then propagate changes elsewhere.
>
> **For AI Agents**: When instructions conflict, trust SSOT over other docs. Log every change in the Update Log.

## Scope

AGDD provides:
- Typer CLI (`agdd`) with flow, agent, data, and MCP commands.
- FastAPI HTTP API (`agdd.api.server`) with governance-aware error handling.
- Agent Runner that orchestrates MAG/SAG lifecycles, skills, and evaluation hooks.
- Catalog of declarative assets (agents, skills, routing, policies, evals).
- Observability stack writing run artefacts to `.runs/` and optional Postgres/Redis backends.

## Terminology

| Term | Definition | Primary Source |
|------|------------|----------------|
| **MAG (Main Agent)** | Orchestrator responsible for task decomposition, delegation, and aggregation. Slug format: `<purpose>-mag`. | `catalog/agents/main/` |
| **SAG (Sub Agent)** | Specialized agent handling scoped work delegated by a MAG. Slug format: `<purpose>-sag`. | `catalog/agents/sub/` |
| **Skill** | Reusable capability invoked via `SkillRuntime`. Declared in registry with optional MCP permissions. | `catalog/registry/skills.yaml` |
| **ExecPlan** | Structured plan document tracking multi-session initiatives. | `docs/development/plans/`, `PLANS.md` |
| **Run Artefact** | Logs, metrics, and summaries generated per execution. | `.runs/agents/<run-id>/` |
| **Governance Gate** | Policy evaluation executed via `agdd flow gate`. | `catalog/policies/` |
| **Plan Router** | Provider/model selection logic for LLM calls. | `agdd.routing.router` |
| **MCP** | Model Context Protocol integration exposing agents/skills as tools or consuming external systems. | `agdd.mcp.*`, `docs/guides/mcp-integration.md` |

## Data Contracts

### Candidate Profile (`catalog/contracts/candidate_profile.schema.json`)
- Used by: `offer-orchestrator-mag`
- Required fields: `id`, `name`, `role`, `experience_years`
- Optional: `level`, `location`, `salary_band`, `preferences`

### Offer Packet (`catalog/contracts/offer_packet.schema.json`)
- Produced by: `offer-orchestrator-mag`
- Sections: `offer` (compensation, benefits), `metadata` (run info), `warnings`, `provenance`
- `metadata.run_id` ties back to observability artefacts

### Compensation Advisor Input (`catalog/contracts/comp_advisor_input.schema.json`)
- Used by: `compensation-advisor-sag`
- Contains `candidate_profile` object validated against candidate schema

### Flow Summary (`agdd/assets/contracts/flow_summary.schema.json`)
- Input for governance gate evaluations
- Key metrics: `runs`, `success_rate`, `avg_latency_ms`, `steps[]`, `mcp.calls`

## API Surface

- **Base prefix**: `/api/v1`
- **Authentication**: Optional bearer token via `AGDD_API_KEY`
- **Endpoints**:
  - `GET /health` – Liveness probe
  - `GET /api/v1/agents` – List registered agent descriptors
  - `POST /api/v1/agents/{slug}/run` – Execute MAG with payload validation
  - `GET /api/v1/runs/{run_id}` – Retrieve run summary
  - `GET /api/v1/runs/{run_id}/logs` – Stream logs
  - `POST /api/v1/github/webhook` – GitHub integration (signature optional)
- **Error schema**: `{ "code": string, "message": string, "details"?: object }`

## Configuration Matrix

| Setting | Description | Default | Location |
|---------|-------------|---------|----------|
| `AGDD_API_PREFIX` | HTTP API base path | `/api/v1` | `agdd.api.config.Settings` |
| `AGDD_STORAGE_BACKEND` | `sqlite` or `postgres` | `sqlite` | `agdd.api.config.Settings` |
| `AGDD_STORAGE_DB_PATH` | SQLite file path | `.agdd/storage.db` | `agdd.api.config.Settings` |
| `AGDD_STORAGE_ENABLE_FTS` | Enable SQLite FTS5 | `true` | `agdd.api.config.Settings` |
| `AGDD_MCP_SERVERS_DIR` | MCP server config directory | `.mcp/servers` | `agdd.mcp.registry` |
| `AGDD_PROVIDER` | Default LLM provider hint | `local` | `agdd.router.Router` |
| `AGDD_MODEL` | Default model override | `None` | `agdd.routing.router` |
| `AGDD_RATE_LIMIT_QPS` | API rate limit | `None` | `agdd.api.rate_limit` |

## Governance Policies

- **Flow Runner Gate**: Policies in `catalog/policies/flow_governance.yaml` set thresholds for success rate, latency, required steps, and MCP error rates.
- **Routing Policies**: `catalog/routing/` describes provider/model selection and fallback tiers.
- **Moderation**: `agdd.moderation` integrates OpenAI omni-moderation; enable via plan metadata when required.
- **Storage Retention**: `agdd.storage` supports vacuum policies (`hot_days`, `max_disk_mb`) invoked via `agdd data vacuum`.

## Observability

- `ObservabilityLogger` (see `src/agdd/observability/logger.py`) writes:
  - `logs.jsonl`: Event stream with span context
  - `metrics.json`: Aggregated metrics (latency, cost, tokens)
  - `summary.json`: Execution metadata (span ids, cost totals)
- Cost tracking persists to JSONL and optional SQLite when `agdd.observability.cost_tracker` is configured.
- Integrations with OpenTelemetry and Langfuse activate via `agdd[observability]` extra.

## Skill Lifecycle

1. Define schema contracts (if needed) under `catalog/contracts/`.
2. Implement async skill function with optional MCP integration.
3. Register in `catalog/registry/skills.yaml`.
4. Add tests under `tests/skills/` or `tests/mcp/`.
5. Document behaviour here and in `SKILL.md`.
6. Update `CHANGELOG.md` and relevant ExecPlan.

## Release Checklist

- Update ExecPlans and confirm all To-do items complete (`PLANS.md`).
- Move changelog items from `[Unreleased]` to a dated release section.
- Tag release (`v<major>.<minor>.<patch>`).
- Publish release notes referencing CLI/API changes, contracts, and docs.

## Dependencies & Integrations

| Integration | Usage | Notes |
|-------------|-------|-------|
| Flow Runner CLI (`flowctl`) | Optional external orchestrator | Detected via `agdd flow available` |
| OpenAI / Anthropic / Google | LLM providers | Selected via routing policy or environment overrides |
| MCP Servers | Expose agents/skills or consume external tools | Configured in `.mcp/servers/*.yaml` |
| Postgres / Redis | Storage & caching backends | Enabled via extras `agdd[postgres]`, `agdd[redis]` |

## Related Documentation

- `AGENTS.md` – Operational instructions for contributors and AI assistants
- `CONTRIBUTING.md` – Contribution workflow, tests, and review process
- `SKILL.md` – Skill development handbook
- `docs/guides/` – Deep dives (MCP integration, cost optimisation, semantic cache, moderation, runner integration)
- `docs/reference/ssot.md` – Extended glossary used by downstream docs

## Update Log

- 2025-10-30: Reconstructed SSOT with canonical terminology, contracts, governance, and integration tables.
