## [Unreleased]
### Added
- Framework repository structure, documentation, and CI guardrails for AG-Driven Development (AGDD)
- AI-first walking skeleton (Typer CLI, echo skill, agent descriptor, contract schema, and pytest coverage)
- Documentation guardrail extension to ensure README/PLANS/SSOT/AGENTS/CHANGELOG are present
- Runner abstraction (`agdd.runners`) with Flow Runner adapter, CLI entry points, and mirrored Flow Runner assets
- Flow Runner observability summary tooling (`observability/summarize_runs.py`) and Typer CLI integration
- Governance artifacts (`contracts/flow_summary.schema.json`, `policies/flow_governance.yaml`) and CLI command (`agdd flow gate`)
- Vendor verification script (`tools/verify_vendor.py`) and runner documentation (`RUNNERS.md`)
- **MAG/SAG Orchestration System v0.1**
  - Agent Runner (`agdd.runners.agent_runner`) for MAG/SAG execution with observability
  - OfferOrchestratorMAG and CompensationAdvisorSAG reference implementations
  - Agent registry system (`agdd.registry`) with YAML-based configuration
  - Contract schemas for candidate profiles, compensation advisors, and offer packets
  - CLI command `agdd agent run` for MAG execution
  - Comprehensive observability: logs.jsonl, metrics.json, summary.json with SLO definitions
  - Three-layer testing strategy (unit/agent/integration) with 63 tests
- **Development Productivity Tools**
  - Agent templates (`agents/_template/mag-template/`, `agents/_template/sag-template/`) for rapid development
  - Flow Runner automated setup script (`scripts/setup-flowrunner.sh`) with Makefile integration
  - Development automation via `Makefile` with 15+ common tasks
- **HTTP API (Phase 1)**
  - FastAPI-powered RESTful API (`agdd.api`) for agent execution
  - Endpoints: `/api/v1/agents` (list/run), `/api/v1/runs` (summary/metrics/logs)
  - Server-Sent Events (SSE) for real-time log streaming
  - OpenAPI/Swagger documentation at `/docs` and `/redoc`
  - API authentication support via bearer token or x-api-key header
  - Run tracking system to identify agent runs from filesystem artifacts
  - Rate limiting (in-memory token bucket + optional Redis for distributed deployments)
  - Configurable QPS limits via `AGDD_RATE_LIMIT_QPS` environment variable
  - API server startup script (`scripts/run-api-server.sh`)
  - Comprehensive curl examples (`examples/api/curl_examples.sh`) with error handling
  - Integration tests for API endpoints (118 total tests)
- **GitHub Integration (Phase 2)**
  - GitHub webhook endpoint (`/api/v1/github/webhook`) with signature verification
  - Comment parser for `@agent-slug {json}` command syntax
  - Support for issue comments, PR review comments, and PR descriptions
  - Automatic agent execution triggered by GitHub comments
  - Result posting back to GitHub as comments (success/error formatting)
  - Event handlers for `issue_comment`, `pull_request_review_comment`, `pull_request`
  - Webhook setup script (`scripts/setup-github-webhook.sh`)
  - GitHub Actions workflow examples (`examples/api/github_actions.yml`)
  - Comprehensive integration tests with signature verification
  - Health check endpoint (`/api/v1/github/health`)
- **Operational Documentation**
  - API reference (`API.md`), GitHub integration guide (`GITHUB.md`), and documented environment template (`.env.example`)
  - Expanded README/AGENTS guidance covering HTTP API usage, SSE streaming, rate limiting, and GitHub automation flows
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
- CLI usage simplified from `uv run python -m agdd.cli` to `uv run agdd` across all documentation
- All documentation updated to reference automated scripts and Makefile instead of manual procedures
### Removed
- Legacy skill-based agent system (`registry/agents/hello.yaml`, `agdd validate`, `agdd run <agent_id>` commands)
- Obsolete `tools/lint_registry.py` (functionality replaced by contract validation in tests)
- Manual Flow Runner setup script `tools/flowrunner_env.sh` (replaced by automated `scripts/setup-flowrunner.sh`)
### Fixed
- Restored Typer CLI `run` command compatibility with positional text arguments while keeping the `--text` option override
- Corrected registry A/B variant to reference an existing AG-Driven Development (AGDD) main agent descriptor
- Ensured wheel builds include bundled schemas and policies so CLI commands succeed after installation
- Hardened GitHub comment parsing to support nested JSON payloads and prevent duplicate execution
- Added Redis failure warnings so rate limiting degradations are observable in production logs
- Wired run summary/log endpoints through the global rate-limiting dependency to keep throttle enforcement consistent
- Phase 1 follow-up bug fixes:
  - Enforced Redis Lua script atomicity to prevent concurrent limit breaches
  - Added timestamp sequence suffixes to eliminate sorted-set collisions
  - Re-raised `HTTPException` instances during Redis failures to preserve status codes
  - Scrubbed API key values from curl examples and logging output
  - Ensured every external route declares the shared `rate_limit_dependency`
- Prevented Flow Runner environment helper from mutating caller shell options and ensured zsh compatibility
- Fixed Flow Runner governance by counting successful runs when `failures` keys are empty
## [0.1.0] - 2025-10-20
### Added
- Initial skeleton (registry/agents.yaml, skills/_template/SKILL.md, contracts/, .mcp/servers/)
### Changed
- None
### Fixed
- None
