# SSOT (Single Source of Truth)
Authoritative source for terminology, policies, and permissions. When conflicts arise, this document wins. Announce changes here first via PR and let other documents reference this canon.

## Glossary
- **Agent**: AI-first orchestrator defined in `registry/agents/*.yaml` that wires skills together to fulfil a task.
- **MAG (Main Agent)**: Top-level orchestrator responsible for task decomposition, delegation to SAGs, and result aggregation. MAG identifiers use the `-mag` suffix (e.g., `offer-orchestrator-mag`).
- **SAG (Sub-Agent)**: Specialized agent focused on domain-specific tasks, invoked by MAGs via delegation. SAG identifiers use the `-sag` suffix (e.g., `compensation-advisor-sag`).
- **Delegation**: The act of a MAG assigning a task to a SAG, encapsulated in a `Delegation` object containing task_id, sag_id, input, and context.
- **A2A Communication**: Agent-to-Agent communication pattern where MAGs orchestrate work by delegating to specialized SAGs, enabling task decomposition and parallel execution.
- **Skill**: Reusable capability packaged under `agdd.skills` (source) and referenced by agents via identifier.
- **Contract**: JSON Schema (stored in `contracts/`) that expresses the invariants for agent and skill descriptors.
- **Registry**: Canonical mapping of tasks -> agents (`registry/agents.yaml`) and skills (`registry/skills.yaml`), plus per-agent descriptors.
- **Walking Skeleton**: Minimal end-to-end path (registry -> contract validation -> skill execution -> logging/CI) proving the AGDD pipeline works.
- **Runner**: Execution boundary defined under `agdd.runners.*` that orchestrates flows for agents. Flow Runner is the default adapter.
- **Run Artifact**: Structured logs emitted to `.runs/agents/<RUN_ID>/` by Flow Runner (e.g., `summary.json`, `runs.jsonl`, `mcp_calls.jsonl`) used for observability and governance.
- **MCP (Model Context Protocol)**: Open protocol for standardizing AI application interactions with external tools and data sources. AGDD integrates MCP servers for filesystem, git, memory, web fetching, and database access.
- **MCP Server**: External service providing tools via the Model Context Protocol (e.g., filesystem operations, git commands, knowledge graph queries).
- **Multi-Provider**: Support for multiple LLM providers (OpenAI, Anthropic, local models) within the same workflow, enabling provider diversity, fallback strategies, and cost optimization.
- **Cost Tracking**: Automatic tracking of token usage and costs per model, agent, and run, persisted to `.runs/costs/costs.jsonl` and `.runs/costs.db`, and queryable via the storage layer.
- **Plan Flags**: Execution toggles (`use_batch`, `use_cache`, `structured_output`, `moderation`) defined on `agdd.routing.router.Plan` and recorded alongside agent runs for auditing.
- **Content Moderator**: The `agdd.security.moderation.ContentModerator` singleton that calls OpenAI's `omni-moderation-latest` before prompts leave AGDD and before completions are published.
- **Flow Runner Python Path**: When Flow Runner is installed in editable mode, `FLOW_RUNNER_PYTHONPATH` must include the `packages/flowrunner/src` and `packages/mcprouter/src` locations so `flowctl` can import its modules.

## Policies
- **AI-first**: Every workflow must be invokable via agents/skills; manual scripts should be wrappers around agent calls.
- **Versioning**: Use semantic versioning (`MAJOR.MINOR.PATCH[-PRERELEASE]`) for agents, skills, and packages.
- **Naming**: Agent identifiers use lowercase hyphen-less slugs (e.g., `hello`), skill identifiers use dotted kebab-case (e.g., `skill.echo`), runner modules live under `agdd.runners.<adapter_name>`.
- **Documentation**: Update `PLANS.md` before touching code, propagate terminology changes here first, and append `CHANGELOG.md` when work is complete.
- **Runner Boundaries**: Flow Runner (`FlowRunner`) is the reference implementation; alternative runners must implement `agdd.runners.base.Runner` and document installation steps.
- **Observability**: `.runs/` artifacts must be summarized via `src/agdd/observability/summarize_runs.py` (or equivalent) before feeding metrics into CI governance stages, capturing success rates, MCP call counts, latency statistics, plan flag decisions, and per-step performance. CI must persist the summary output for downstream Multi Agent Governance checks, and `.runs/costs/` must be archived for expense governance.
- **Moderation**: Do not disable `AGDD_MODERATION_ENABLED` in production. Any exception requires documenting the alternative safety layer and updating `docs/guides/multi-provider.md`.
- **Packaging**: Wheel builds must include schemas and governance policies under `agdd/assets/`. After modifying bundled resources, run `uv build` and install the wheel in a temporary virtual environment to confirm `importlib.resources` loads succeed.
- **Governance**: `policies/flow_governance.yaml` defines baseline thresholds. Any change to thresholds or summary structure requires concurrent updates to CLI (`agdd flow gate`) and `contracts/flow_summary.schema.json`.
- **Vendor Assets**: Flow Runner schemas and examples are vendored; run `uv run python tools/verify_vendor.py` locally and in CI to detect drift.
