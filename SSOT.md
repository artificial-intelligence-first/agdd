# SSOT (Single Source of Truth)
Authoritative source for terminology, policies, and permissions. When conflicts arise, this document wins. Announce changes here first via PR and let other documents reference this canon.

## Glossary
- **Agent**: AI-first orchestrator defined in `registry/agents/*.yaml` that wires skills together to fulfil a task.
- **Skill**: Reusable capability packaged under `agdd.skills` (source) and referenced by agents via identifier.
- **Contract**: JSON Schema (stored in `contracts/`) that expresses the invariants for agent and skill descriptors.
- **Registry**: Canonical mapping of tasks -> agents (`registry/agents.yaml`) and skills (`registry/skills.yaml`), plus per-agent descriptors.
- **Walking Skeleton**: Minimal end-to-end path (registry -> contract validation -> skill execution -> logging/CI) proving the AGDD pipeline works.
- **Runner**: Execution boundary defined under `agdd.runners.*` that orchestrates flows for agents. Flow Runner is the default adapter.
- **Run Artifact**: Structured logs emitted to `.runs/<RUN_ID>/` by Flow Runner (e.g., `summary.json`, `runs.jsonl`, `mcp_calls.jsonl`) used for observability and governance.
- **Flow Runner Python Path**: When Flow Runner is installed in editable mode, `FLOW_RUNNER_PYTHONPATH` must include the `packages/flowrunner/src` and `packages/mcprouter/src` locations so `flowctl` can import its modules.

## Policies
- **AI-first**: Every workflow must be invokable via agents/skills; manual scripts should be wrappers around agent calls.
- **Versioning**: Use semantic versioning (`MAJOR.MINOR.PATCH[-PRERELEASE]`) for agents, skills, and packages.
- **Naming**: Agent identifiers use lowercase hyphen-less slugs (e.g., `hello`), skill identifiers use dotted kebab-case (e.g., `skill.echo`), runner modules live under `agdd.runners.<adapter_name>`.
- **Documentation**: Update `PLANS.md` before touching code, propagate terminology changes here first, and append `CHANGELOG.md` when work is complete.
- **Runner Boundaries**: Flow Runner (`FlowRunner`) is the reference implementation; alternative runners must implement `agdd.runners.base.Runner` and document installation steps.
- **Observability**: `.runs/` artifacts must be summarized via `observability/summarize_runs.py` (or equivalent) before feeding metrics into CI governance stages, capturing success rates, MCP call counts, latency statistics, and per-step performance. CI must persist the summary output for downstream Multi Agent Governance checks.
- **Packaging**: Wheel builds must include schemas and governance policies under `agdd/assets/`. After modifying bundled resources, run `uv build` and install the wheel in a temporary virtual environment to confirm `importlib.resources` loads succeed.
- **Governance**: `policies/flow_governance.yaml` defines baseline thresholds. Any change to thresholds or summary structure requires concurrent updates to `tools/gate_flow_summary.py` and `contracts/flow_summary.schema.json`.
- **Vendor Assets**: Flow Runner schemas and examples are vendored; run `uv run python tools/verify_vendor.py` locally and in CI to detect drift.
