# AG-Driven Development (AGDD) Framework (ExecPlan)
This ExecPlan is a living document. Keep Progress / Decision Log current.

## Purpose / Big Picture
Establish the minimal AG-Driven Development (AGDD) repository skeleton so future AG-Driven Development (AGDD) work starts from a compliant baseline.

## To-do
- Outline next steps for CI observability once framework foundation is complete

## Progress
- Initialized repo (`git init`, uv tooling, directories) and switched to feature branch
- Authored baseline documentation (AGENTS, SSOT, README) and registered agents/skills wiring
- Added skill templates, MCP server reference, contracts, and policy checks including CI workflow
- Validated documentation guardrails and contracts via `uv run python tools/check_docs.py` and `uv run -m pytest -q`
- Standardized all implementation-facing documentation to English upon request
- Removed local-only scaffolding (e.g., example `main.py`, `.venv`, `.pytest_cache`) to keep the repository publication-ready
- Unified terminology to "AG-Driven Development (AGDD)" across public documentation
- Re-ran documentation checks and contract tests after terminology updates to confirm a clean state
- Fixed registry A/B variant routing so both arms reference the available main agent descriptor

## Surprises & Discoveries
None so far.

## Decision Log
- Followed provided framework templates verbatim to stay aligned with governing instructions
- Introduced `contracts/salary_band.json` so dependent skills have explicit schema coverage
- Converted repository language to English to maintain consistency with implementation standards
- Removed generated local runtime artifacts from version control scope while keeping `.mcp/.env.mcp` untouched as requested
- Applied repository-wide rename to "AG-Driven Development (AGDD)" terminology
- Resolved misconfiguration that pointed an A/B variant at a non-existent main agent version

## Outcomes & Retrospective
Framework deliverables are in place with passing tests and policy checks, ready for initial review and iteration.

## Context and Orientation
Work performed inside freshly initialized `agdd` repository under feature branch `feat/bootstrap-agdd`.

## Plan of Work
Iteratively add documentation, configuration, code, and automation needed by the framework specification, validating along the way.

## Concrete Steps
1. Finish authoring docs and registry definitions
2. Add agent and skill templates with supporting directories
3. Implement contracts, tests, and MCP server configuration
4. Create CI workflow including doc guards and pytest run
5. Verify tests locally and finalize documentation updates

## Validation & Acceptance
Acceptance requires tests passing via `uv run -m pytest -q` and CI workflow covering doc and changelog checks. Both commands were executed locally and succeeded.

## Idempotence & Recovery
All framework commands are idempotent; re-running them should not corrupt state. Git history and uv lockfile provide recovery points.

## Artifacts & Notes
- Repository managed with uv 0.x environment using Python 3.12.

## Interfaces & Dependencies
- Relies on uv tooling for dependency management and pytest for validation.
