# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- **Pluggable Storage Layer (Phase 1)**
  - Storage abstraction layer (`agdd.storage`) with capability-based backend interface
  - Event envelope data model with strongly-typed common fields + flexible JSON payloads
  - SQLite backend (`SQLiteStorageBackend`) with FTS5 full-text search support
  - CLI commands for data management:
    - `agdd data init` - Initialize storage backend
    - `agdd data query` - Query runs and events
    - `agdd data search` - Full-text search across events (requires FTS5)
    - `agdd data vacuum` - Clean up old data with retention policies
    - `agdd data archive` - Archive to external storage (future implementation)
  - Configuration management for storage settings (backend type, database path, lifecycle policies)
  - Migration script (`ops/scripts/migrate_to_storage.py`) to import legacy `.runs/agents/` data
  - Comprehensive documentation (`docs/storage.md`) with usage examples and best practices
  - Test suite for SQLite backend with async support
  - Support for multiple event types: log, mcp.call, metric, delegation, artifact
  - Prepared for future backends: PostgreSQL/TimescaleDB, ClickHouse
  - **Note**: Storage layer is for CLI/API data management; agents continue using `ObservabilityLogger`
- Framework repository structure, documentation, and CI guardrails for AG-Driven Development (AGDD)
- AI-first walking skeleton (Typer CLI, echo skill, agent descriptor, contract schema, and pytest coverage)
- Documentation guardrail extension to ensure README/PLANS/SSOT/AGENTS/CHANGELOG are present
- Runner abstraction (`agdd.runners`) with Flow Runner adapter, CLI entry points, and mirrored Flow Runner assets
- Flow Runner observability summary tooling (`observability/summarize_runs.py`) and Typer CLI integration
- Governance artifacts (`catalog/contracts/flow_summary.schema.json`, `catalog/policies/flow_governance.yaml`) and CLI command (`agdd flow gate`)
- Vendor verification script (`ops/tools/verify_vendor.py`) and runner documentation (`docs/guides/runner-integration.md`)
- **MAG/SAG Orchestration System v0.1**
  - Agent Runner (`agdd.runners.agent_runner`) for MAG/SAG execution with observability
  - OfferOrchestratorMAG and CompensationAdvisorSAG reference implementations
  - Agent registry system (`agdd.registry`) with YAML-based configuration
  - Contract schemas for candidate profiles, compensation advisors, and offer packets
  - CLI command `agdd agent run` for MAG execution
  - Comprehensive observability: logs.jsonl, metrics.json, summary.json with SLO definitions
  - Three-layer testing strategy (unit/agent/integration) with 63 tests
- **Development Productivity Tools**
  - Agent templates (`catalog/agents/_template/mag-template/`, `catalog/agents/_template/sag-template/`) for rapid development
  - Flow Runner automated setup script (`ops/scripts/setup-flowrunner.sh`) with Makefile integration
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
  - API server startup script (`ops/scripts/run-api-server.sh`)
  - Comprehensive curl examples (`examples/api/curl_examples.sh`) with error handling
  - Integration tests for API endpoints (118 total tests)
- **GitHub Integration (Phase 2)**
  - GitHub webhook endpoint (`/api/v1/github/webhook`) with signature verification
  - Comment parser for `@agent-slug {json}` command syntax
  - Support for issue comments, PR review comments, and PR descriptions
  - Automatic agent execution triggered by GitHub comments
  - Result posting back to GitHub as comments (success/error formatting)
  - Event handlers for `issue_comment`, `pull_request_review_comment`, `pull_request`
  - Webhook setup script (`ops/scripts/setup-github-webhook.sh`)
  - GitHub Actions workflow examples (`examples/api/github_actions.yml`)
  - Comprehensive integration tests with signature verification
  - Health check endpoint (`/api/v1/github/health`)
  - Comprehensive documentation (`docs/guides/api-usage.md`, `docs/guides/github-integration.md`) and `.env.example` template

### Changed
- **Repository Cleanup**: Removed deprecated agent directories (`offer-orchestrator`, `compensation-advisor`) in favor of standardized `-mag`/`-sag` naming convention
- **Registry Updates**: Updated `catalog/registry/agents.yaml` to reference only current agent implementations
- **Build Artifacts**: Cleaned up Python cache files (`__pycache__`, `*.pyc`) and build artifacts (`.egg-info`)
- Hardened typing across registries, runners, governance gate, and observability helpers, enabling `mypy --strict` to pass for `agdd`, `tests`, and `ops/tools`
- Added type stub dependencies (`types-PyYAML`, `types-jsonschema`, `types-aiofiles`, `types-redis`) and tightened fixtures/tests to remove `Any` leakage in rate limiting and orchestration flows
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
- Legacy agent directories without standardized naming conventions
- Temporary verification report (`VERIFICATION_REPORT.md`)
- Python cache files and build artifacts
- Legacy skill-based agent system (`catalog/registry/agents/hello.yaml`, `agdd validate`, `agdd run <agent_id>` commands)
- Obsolete `ops/tools/lint_registry.py` (functionality replaced by contract validation in tests)
- Manual Flow Runner setup script `ops/tools/flowrunner_env.sh` (replaced by automated `ops/scripts/setup-flowrunner.sh`)

### Fixed
- Restored Typer CLI `run` command compatibility with positional text arguments while keeping the `--text` option override
- Corrected registry A/B variant to reference an existing AG-Driven Development (AGDD) main agent descriptor
- Ensured wheel builds include bundled schemas and policies so CLI commands succeed after installation
- Prevented Flow Runner environment helper from mutating caller shell options and ensured zsh compatibility
- Fixed Flow Runner governance by counting successful runs when `failures` keys are empty
- HTTP API hardening from Codex reviews:
  - Lua script now guarantees atomic Redis rate limiting
  - Unique timestamp sequence members prevent collision during bursts
  - HTTP exceptions from the rate limiter bubble up instead of being swallowed
  - Rate limit dependency is applied to all FastAPI routes, including GitHub webhook handlers
  - Example scripts avoid printing API keys during demonstrations
  - Removed unused imports and variables (ruff clean)
  - Fixed .env.example to comment out empty values (prevents Pydantic validation errors)

## [0.1.0] - 2025-10-20
### Added
- Initial skeleton (catalog/registry/agents.yaml, catalog/skills/_template/SKILL.md, catalog/contracts/, .mcp/servers/)
### Changed
- None
### Fixed
- None

[Unreleased]: https://github.com/artificial-intelligence-first/agdd/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/artificial-intelligence-first/agdd/releases/tag/v0.1.0