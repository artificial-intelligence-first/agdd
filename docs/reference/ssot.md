---
title: SSOT (Single Source of Truth) - Local Reference
last_synced: 2025-10-24
source_of_truth: https://github.com/artificial-intelligence-first/ssot/blob/main/topics/SSOT.md
description: Local reference for AGDD-specific terminology and policies. For canonical definitions, see the SSOT repository.
change_log:
  - 2025-10-24: Added SSOT repository reference and front-matter
---

# SSOT (Single Source of Truth)

**Note:** This document provides AGDD-specific terminology. For canonical definitions and cross-project policies, refer to the [SSOT repository](https://github.com/artificial-intelligence-first/ssot/blob/main/topics/SSOT.md).

Authoritative source for terminology, policies, and permissions. When conflicts arise, this document wins. Announce changes here first via PR and let other documents reference this canon.

## Glossary
- **Agent**: AI-first orchestrator defined in `registry/agents/*.yaml` that wires skills together to fulfil a task.
- **MAG (Main Agent)**: Top-level orchestrator responsible for task decomposition, delegation to SAGs, and result aggregation. MAG identifiers use the `-mag` suffix (e.g., `offer-orchestrator-mag`).
- **SAG (Sub-Agent)**: Specialized agent focused on domain-specific tasks, invoked by MAGs via delegation. SAG identifiers use the `-sag` suffix (e.g., `compensation-advisor-sag`).
- **Delegation**: The act of a MAG assigning a task to a SAG, encapsulated in a `Delegation` object containing task_id, sag_id, input, and context.
- **A2A Communication**: Agent-to-Agent communication pattern where MAGs orchestrate work by delegating to specialized SAGs, enabling task decomposition and parallel execution.
- **Skill**: Reusable capability packaged under `agdd.skills` (source) and referenced by agents via identifier.
- **Eval Hook**: Quality and safety validation layer that executes before (pre_eval) or after (post_eval) agent execution to verify input validity, output quality, consistency, and safety constraints. Evaluators are defined in `catalog/evals/{slug}/eval.yaml`.
- **Pre-Eval**: Evaluation hook executed before agent processing to validate input data quality, format compliance, and safety constraints. Prevents invalid inputs from consuming agent resources.
- **Post-Eval**: Evaluation hook executed after agent processing to validate output quality, completeness, consistency, and safety. Ensures agents produce valid, high-quality results before propagation to downstream systems.
- **Evaluation Metric**: Individual quality check within an evaluator (e.g., `salary_range_check`, `consistency_check`) that returns a score (0.0-1.0), pass/fail status, and detailed diagnostics. Metrics are implemented as Python functions in `catalog/evals/{slug}/metric/validator.py`.
- **Evaluation Pipeline**: End-to-end validation flow integrated into AgentRunner: MAG → Pre-Eval → SAG Execution → Post-Eval → Observability. Eval results are logged to `ObservabilityLogger` for auditing and quality monitoring.
- **Contract**: JSON Schema (stored in `contracts/`) that expresses the invariants for agent and skill descriptors.
- **Registry**: Canonical mapping of tasks -> agents (`registry/agents.yaml`), skills (`registry/skills.yaml`), and evaluators (`catalog/evals/`). Provides load_agent(), load_skill(), and load_eval() methods for descriptor resolution.
- **Walking Skeleton**: Minimal end-to-end path (registry -> contract validation -> skill execution -> logging/CI) proving the AGDD pipeline works.
- **Runner**: Execution boundary defined under `agdd.runners.*` that orchestrates flows for agents. Flow Runner is the default adapter.
- **Run Artifact**: Structured logs emitted to `.runs/agents/<RUN_ID>/` by Flow Runner (e.g., `summary.json`, `runs.jsonl`, `mcp_calls.jsonl`) used for observability and governance.
- **MCP (Model Context Protocol)**: Open protocol for standardizing AI application interactions with external tools and data sources. AGDD integrates MCP servers for filesystem, git, memory, web fetching, and database access.
- **MCP Server**: External service providing tools via the Model Context Protocol (e.g., filesystem operations, git commands, knowledge graph queries).
- **Multi-Provider**: Support for multiple LLM providers (OpenAI, Anthropic, local models) within the same workflow, enabling provider diversity, fallback strategies, and cost optimization.
- **Cost Tracking**: Automatic tracking of token usage and costs per model, agent, and run, persisted to `.runs/costs/costs.jsonl` and `.runs/costs.db`, and queryable via the storage layer.
- **Plan Flags**: Execution toggles (`use_batch`, `use_cache`, `structured_output`, `moderation`) defined on `agdd.routing.router.Plan` and recorded alongside agent runs for auditing.
- **Semantic Cache**: Vector similarity search-based caching using FAISS or Redis backends to reduce costs by avoiding redundant LLM calls for similar prompts. Eliminates O(N) linear scans through top-K nearest neighbor search.
- **Content Moderation**: OpenAI omni-moderation-latest integration for input/output content safety checks. Supports fail-open (permissive on errors) and fail-closed (strict on errors) strategies.
- **Batch API**: OpenAI Batch API integration providing 50% cost reduction for non-realtime workloads with 24-hour completion windows. Supports both `/v1/chat/completions` and `/v1/responses` endpoints.
- **Responses API**: Modern OpenAI API format supporting structured outputs, tool calls, and multimodal content. Local providers prefer Responses API and automatically fall back to chat completions for legacy endpoints.
- **Flow Runner Python Path**: When Flow Runner is installed in editable mode, `FLOW_RUNNER_PYTHONPATH` must include the `packages/flowrunner/src` and `packages/mcprouter/src` locations so `flowctl` can import its modules.

## Policies
- **AI-first**: Every workflow must be invokable via agents/skills; manual scripts should be wrappers around agent calls.
- **Versioning**: Use semantic versioning (`MAJOR.MINOR.PATCH[-PRERELEASE]`) for agents, skills, and packages.
- **Naming**: Agent identifiers use lowercase hyphen-less slugs (e.g., `hello`), skill identifiers use dotted kebab-case (e.g., `skill.echo`), runner modules live under `agdd.runners.<adapter_name>`.
- **Documentation**: Update `PLANS.md` before touching code, propagate terminology changes here first, and append `CHANGELOG.md` when work is complete.
- **Runner Boundaries**: Flow Runner (`FlowRunner`) is the reference implementation; alternative runners must implement `agdd.runners.base.Runner` and document installation steps.
- **Observability**: `.runs/` artifacts must be summarized via `src/agdd/observability/summarize_runs.py` (or equivalent) before feeding metrics into CI governance stages, capturing success rates, MCP call counts, latency statistics, plan flag decisions, and per-step performance. CI must persist the summary output for downstream Multi Agent Governance checks, and `.runs/costs/` must be archived for expense governance. Eval Hook results (pre_eval and post_eval) are logged to `ObservabilityLogger` for quality monitoring and auditing.
- **Evaluation**: Evaluators are defined in `catalog/evals/{slug}/eval.yaml` with metrics implemented in `metric/validator.py`. Each evaluator specifies `hook_type` (pre_eval or post_eval), `target_agents` (which SAGs it applies to), and `metrics` (individual quality checks with thresholds and weights). AgentRunner automatically executes applicable evaluators during SAG invocation and logs results to observability layer. Evaluators support fail-open (log failures but continue) and fail-closed (block execution on critical failures) strategies.
- **Packaging**: Wheel builds must include schemas and governance policies under `agdd/assets/`. After modifying bundled resources, run `uv build` and install the wheel in a temporary virtual environment to confirm `importlib.resources` loads succeed.
- **Governance**: `policies/flow_governance.yaml` defines baseline thresholds. Any change to thresholds or summary structure requires concurrent updates to CLI (`agdd flow gate`) and `contracts/flow_summary.schema.json`.
- **Vendor Assets**: Flow Runner schemas and examples are vendored; run `uv run python tools/verify_vendor.py` locally and in CI to detect drift.
