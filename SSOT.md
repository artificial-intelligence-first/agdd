# SSOT (Single Source of Truth)

Authoritative source for AGDD terminology, policies, and permissions. When conflicts arise between documentation sources, this document takes precedence. Announce changes here first via PR and let other documents reference this canon.

## Glossary

### Agent & Orchestration Concepts
- **Agent**: AI-first orchestrator defined in `registry/agents/*.yaml` that wires skills together to fulfil a task.
- **MAG (Main Agent)**: Top-level orchestrator responsible for task decomposition, delegation to SAGs, and result aggregation. MAG identifiers use the `-mag` suffix (e.g., `offer-orchestrator-mag`).
- **SAG (Sub-Agent)**: Specialized agent focused on domain-specific tasks, invoked by MAGs via delegation. SAG identifiers use the `-sag` suffix (e.g., `compensation-advisor-sag`).
- **Delegation**: The act of a MAG assigning a task to a SAG, encapsulated in a `Delegation` object containing task_id, sag_id, input, and context.
- **A2A Communication**: Agent-to-Agent communication pattern where MAGs orchestrate work by delegating to specialized SAGs, enabling task decomposition and parallel execution.
- **Skill**: Reusable capability packaged under `agdd.skills` (source) and referenced by agents via identifier.

### Quality & Evaluation
- **Eval Hook**: Quality and safety validation layer that executes before (pre_eval) or after (post_eval) agent execution to verify input validity, output quality, consistency, and safety constraints. Evaluators are defined in `catalog/evals/{slug}/eval.yaml`.
- **Pre-Eval**: Evaluation hook executed before agent processing to validate input data quality, format compliance, and safety constraints. Prevents invalid inputs from consuming agent resources.
- **Post-Eval**: Evaluation hook executed after agent processing to validate output quality, completeness, consistency, and safety. Ensures agents produce valid, high-quality results before propagation to downstream systems.
- **Evaluation Metric**: Individual quality check within an evaluator (e.g., `salary_range_check`, `consistency_check`) that returns a score (0.0-1.0), pass/fail status, and detailed diagnostics. Metrics are implemented as Python functions in `catalog/evals/{slug}/metric/validator.py`.
- **Evaluation Pipeline**: End-to-end validation flow integrated into AgentRunner: MAG → Pre-Eval → SAG Execution → Post-Eval → Observability. Eval results are logged to `ObservabilityLogger` for auditing and quality monitoring.

### Framework Components
- **Contract**: JSON Schema (stored in `contracts/`) that expresses the invariants for agent and skill descriptors.
- **Registry**: Canonical mapping of tasks → agents (`registry/agents.yaml`), skills (`registry/skills.yaml`), and evaluators (`catalog/evals/`). Provides load_agent(), load_skill(), and load_eval() methods for descriptor resolution.
- **Walking Skeleton**: Minimal end-to-end path (registry → contract validation → skill execution → logging/CI) proving the AGDD pipeline works.
- **Runner**: Execution boundary defined under `agdd.runners.*` that orchestrates flows for agents. Flow Runner is the default adapter.
- **Run Artifact**: Structured logs emitted to `.runs/agents/<RUN_ID>/` by Flow Runner (e.g., `summary.json`, `runs.jsonl`, `mcp_calls.jsonl`) used for observability and governance.

### Integration & Protocols
- **MCP (Model Context Protocol)**: Open protocol for standardizing AI application interactions with external tools and data sources. AGDD integrates MCP servers for filesystem, git, memory, web fetching, and database access.
- **MCP Server**: External service providing tools via the Model Context Protocol (e.g., filesystem operations, git commands, knowledge graph queries).

### Multi-Provider & Cost Management
- **Multi-Provider**: Support for multiple LLM providers (OpenAI, Anthropic, Google, local models) within the same workflow, enabling provider diversity, fallback strategies, and cost optimization.
- **Cost Tracking**: Automatic tracking of token usage and costs per model, agent, and run, persisted to `.runs/costs/costs.jsonl` and `.runs/costs.db`, and queryable via the storage layer.
- **Plan Flags**: Execution toggles (`use_batch`, `use_cache`, `structured_output`, `moderation`) defined on `agdd.routing.router.Plan` and recorded alongside agent runs for auditing.

### Optimization Features
- **Semantic Cache**: Vector similarity search-based caching using FAISS or Redis backends to reduce costs by avoiding redundant LLM calls for similar prompts. Eliminates O(N) linear scans through top-K nearest neighbor search.
- **Content Moderation**: OpenAI omni-moderation-latest integration for input/output content safety checks. Supports fail-open (permissive on errors) and fail-closed (strict on errors) strategies.
- **Batch API**: OpenAI Batch API integration providing 50% cost reduction for non-realtime workloads with 24-hour completion windows. Supports both `/v1/chat/completions` and `/v1/responses` endpoints.
- **Responses API**: Modern OpenAI API format supporting structured outputs, tool calls, and multimodal content. Local providers prefer Responses API and automatically fall back to chat completions for legacy endpoints.

### Development & Build
- **Flow Runner Python Path**: When Flow Runner is installed in editable mode, `FLOW_RUNNER_PYTHONPATH` must include the `packages/flowrunner/src` and `packages/mcprouter/src` locations so `flowctl` can import its modules.

## Policies

### Development Philosophy
- **AI-first**: Every workflow must be invokable via agents/skills; manual scripts should be wrappers around agent calls.
- **Documentation**: Update `PLANS.md` before touching code, propagate terminology changes here first, and append `CHANGELOG.md` when work is complete.

### Naming Conventions
- **Versioning**: Use semantic versioning (`MAJOR.MINOR.PATCH[-PRERELEASE]`) for agents, skills, and packages.
- **Naming**:
  - Agent identifiers use lowercase hyphen-less slugs (e.g., `hello`)
  - Skill identifiers use dotted kebab-case (e.g., `skill.echo`)
  - Runner modules live under `agdd.runners.<adapter_name>`
  - MAG identifiers end with `-mag` suffix
  - SAG identifiers end with `-sag` suffix

### Runner & Execution
- **Runner Boundaries**: Flow Runner (`FlowRunner`) is the reference implementation; alternative runners must implement `agdd.runners.base.Runner` and document installation steps.

### Observability & Quality
- **Observability**: `.runs/` artifacts must be summarized via `src/agdd/observability/summarize_runs.py` (or equivalent) before feeding metrics into CI governance stages, capturing success rates, MCP call counts, latency statistics, plan flag decisions, and per-step performance. CI must persist the summary output for downstream Multi Agent Governance checks, and `.runs/costs/` must be archived for expense governance. Eval Hook results (pre_eval and post_eval) are logged to `ObservabilityLogger` for quality monitoring and auditing.

- **Evaluation**: Evaluators are defined in `catalog/evals/{slug}/eval.yaml` with metrics implemented in `metric/validator.py`. Each evaluator specifies `hook_type` (pre_eval or post_eval), `target_agents` (which SAGs it applies to), and `metrics` (individual quality checks with thresholds and weights). AgentRunner automatically executes applicable evaluators during SAG invocation and logs results to observability layer. Evaluators support fail-open (log failures but continue) and fail-closed (block execution on critical failures) strategies.

### Packaging & Distribution
- **Packaging**: Wheel builds must include schemas and governance policies under `agdd/assets/`. After modifying bundled resources, run `uv build` and install the wheel in a temporary virtual environment to confirm `importlib.resources` loads succeed.

### Governance & Compliance
- **Governance**: `policies/flow_governance.yaml` defines baseline thresholds. Any change to thresholds or summary structure requires concurrent updates to CLI (`agdd flow gate`) and `contracts/flow_summary.schema.json`.

### Vendor Management
- **Vendor Assets**: Flow Runner schemas and examples are vendored; run `uv run python tools/verify_vendor.py` locally and in CI to detect drift.

## What Belongs in SSOT

### ✅ Include
- Canonical definitions and terminology
- Data schemas and API contracts
- Security policies and retention rules
- Standard workflows and approval processes
- Architecture decisions with rationale
- Environment configuration details
- Naming conventions and standards
- Quality thresholds and governance rules

### ❌ Exclude
- Implementation code details
- Tutorials or guides (use docs/guides/)
- Project status updates (use PLANS.md)
- Task tracking items (use issue tracker)
- Personal notes or drafts
- Version history (use CHANGELOG.md)
- Development procedures (use AGENTS.md)

## Integration with Other Documents

### AGENTS.md
AGENTS.md references SSOT definitions in procedural steps:
- Use SSOT terminology in command examples
- Reference SSOT for naming conventions
- Link to SSOT for policy details

### CHANGELOG.md
CHANGELOG.md tracks changes to SSOT-defined items:
- Document terminology additions/changes
- Record policy updates
- Note schema modifications

### PLANS.md
ExecPlans cite SSOT terminology consistently:
- Use canonical definitions
- Follow naming conventions
- Respect documented policies
- Introduce new concepts to SSOT when discovered

### SKILL.md
Skills reference SSOT for domain knowledge:
- Use standard terminology
- Follow contract schemas
- Respect quality policies

## Practical Workflow

When updating SSOT-related information:

1. **Modify SSOT first**: Add or update definitions here
2. **Propagate changes**: Update dependent documentation (AGENTS.md, guides)
3. **Update implementation**: Modify code to align with new definitions
4. **Communicate changes**: Update CHANGELOG.md and notify stakeholders
5. **Create PR**: Follow standard review process

## SSOT Characteristics

### Authoritative
- The canonical record where conflicts resolve in this document's favor
- Designated as the definitive source by the team
- Changes require PR review and approval

### Accessible
- Easily readable by humans and machines
- Well-known location (repository root)
- Plain text format (Markdown)
- Version controlled with audit trail

### Versioned
- Changes tracked via version control
- Complete audit trail of modifications
- Linked to specific commits and PRs

### Maintained
- Regular reviews to prevent staleness
- Clear ownership (AGDD Core Team)
- Updated proactively with system changes

## Review & Maintenance

### Review Schedule
- **Quarterly**: Comprehensive terminology review
- **Per Feature**: Update SSOT before implementing new features
- **Per Bug**: Verify SSOT accuracy after bug fixes reveal misalignment

### Ownership
- **Primary Owner**: AGDD Core Team
- **Contributors**: All team members via PR
- **Reviewers**: At least one core team member for PR approval

### Change Process
1. Propose changes via PR with rationale
2. Update affected documentation references
3. Request review from core team member
4. Merge after approval
5. Update CHANGELOG.md with change summary
6. Communicate to team if breaking change

## Common Mistakes to Avoid

### ❌ Don't
- Store implementation details (use code comments)
- Include temporary project status (use PLANS.md)
- Document procedures (use AGENTS.md)
- Mix multiple source-of-truth concepts
- Let definitions drift from implementation

### ✅ Do
- Keep definitions clear and concise
- Update SSOT before propagating changes
- Reference SSOT from other documents
- Maintain terminology consistency
- Review and update regularly

## Questions?

For questions about SSOT or this document:
- See canonical SSOT guide: https://github.com/artificial-intelligence-first/ssot/blob/main/files/SSOT.md
- Open an issue with the `documentation` label
- Ask in team chat with @agdd-core

---

**Last Updated**: 2025-10-29
**Maintained By**: AGDD Core Team
**Changes**: See CHANGELOG.md for document revision history
