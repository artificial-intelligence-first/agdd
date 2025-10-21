## [Unreleased]
### Added
- Framework repository structure, documentation, and CI guardrails for AG-Driven Development (AGDD)
- AI-first walking skeleton (Typer CLI, echo skill, agent descriptor, contract schema, and pytest coverage)
- Documentation guardrail extension to ensure README/PLANS/SSOT/AGENTS/CHANGELOG are present
- Runner abstraction (`agdd.runners`) with Flow Runner adapter, CLI entry points, and mirrored Flow Runner assets
- Flow Runner observability summary tooling (`observability/summarize_runs.py`) and Typer CLI integration
- Governance artifacts (`contracts/flow_summary.schema.json`, `policies/flow_governance.yaml`) and gating tool (`tools/gate_flow_summary.py`) with CLI support
- Vendor verification script (`tools/verify_vendor.py`) and runner documentation (`RUNNERS.md`)
- Registry linter (`tools/lint_registry.py`) with pytest coverage for duplicate IDs and missing skills
- Flow Runner environment helper (`tools/flowrunner_env.sh`) for bash/zsh shells
### Changed
- Updated documentation to ensure English-only, publication-ready guidance
- Refined project metadata and removed sample runtime scaffolding
- Unified naming to AG-Driven Development (AGDD) across all public documents
- Expanded project dependencies (Typer, Pydantic, PyYAML) and dev tooling configuration for uv workflows
- Refreshed README, AGENTS, and SSOT to describe the AI Agent-first development loop
- Reworked GitHub Actions workflow with dedicated Flow Runner and Multi Agent Governance jobs
- Documented Flow Runner editable-install workflow and enriched observability metrics (latency, MCP calls)
- Flow Runner summaries now emit per-step statistics, support file output for governance, and are generated automatically in CI
- CI Flow Runner job now enforces governance thresholds and publishes summary artifacts
- Observability summary enriched with error taxonomy, MCP tokens/cost, and per-model aggregates
- README, AGENTS, PLANS, RUNNERS, and SSOT refreshed to document packaging workflow and repository layout
- Flow governance policy now enforces `min_runs` / `required_steps`, and Flow Runner availability reports capability metadata
- CI core workflow builds distributions, verifies wheel assets, and runs registry linting prior to tests
- Flow summary aggregator treats empty failure logs as success and recognises success status variants
### Fixed
- Corrected registry A/B variant to reference an existing AG-Driven Development (AGDD) main agent descriptor
- Ensured wheel builds include bundled schemas and policies so CLI commands succeed after installation
- Prevented Flow Runner environment helper from mutating caller shell options and ensured zsh compatibility
- Fixed Flow Runner governance by counting successful runs when `failures` keys are empty
- Flow Runner validation now shells out to `flowctl validate` rather than `run --dry-run`, ensuring CLI checks match upstream behavior
## [0.1.0] - 2025-10-20
### Added
- Initial skeleton (registry/agents.yaml, skills/_template/SKILL.md, contracts/, .mcp/servers/)
### Changed
- None
### Fixed
- None
