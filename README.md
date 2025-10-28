# AG-Driven Development (AGDD) Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![CI Status](https://img.shields.io/github/actions/workflow/status/artificial-intelligence-first/agdd/ci.yml?branch=main&label=CI)](https://github.com/artificial-intelligence-first/agdd/actions)

A comprehensive framework for building, executing, and governing AI agent-driven workflows with built-in quality controls and observability.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Usage](#usage)
- [Documentation](#documentation)
- [Development](#development)
- [Contributing](#contributing)

## Overview

The AGDD Framework enables developers to build and manage automated agent-driven workflows with built-in quality controls and observability.

**Key Capabilities:**
- AI-First Development: Build workflows invokable via agents and skills
- Multiple Entry Points: CLI, HTTP API, and GitHub integration
- Comprehensive Observability: Track execution metrics, token usage, and costs
- Governance & Policy: Enforce quality thresholds and compliance checks
- Pluggable Architecture: Integrate with Flow Runner or custom execution engines
- Contract-Driven Design: JSON Schema validation for all data structures

## Features

### Core Infrastructure
- Agent Registry: Centralized management of agent descriptors and task routing
- Skills Framework: Reusable, composable skills for agent capabilities
- Contract Verification: Automated JSON Schema validation
- CLI Interface: Typer-powered command-line tools
- HTTP API: FastAPI-powered RESTful API with OpenAPI/Swagger documentation
- MCP Server: Expose agents as MCP tools for Claude Desktop and other MCP clients

### Advanced Capabilities
- Runner Plugins: Pluggable execution engines (Flow Runner included)
- MAG/SAG Architecture: Main and Sub-Agent orchestration patterns
- Observability: Comprehensive metrics, traces, and cost tracking with OpenTelemetry + Langfuse
- Plan-Aware Routing: Agent Runner respects `Plan` flags (`use_batch`, `use_cache`, `structured_output`, `moderation`) and annotates runs for auditability
- Semantic Cache: Vector similarity search with FAISS/Redis backends (no O(N) scans)
- Content Moderation: OpenAI omni-moderation-latest with fail-open/fail-closed strategies
- Batch API: 50% cost reduction via OpenAI Batch API (24h completion window)
- Local LLM Fallback: Responses API preference with automatic chat completions downgrade for legacy endpoints
- Governance Gates: Policy-based validation and compliance checks

### Developer Experience
- Type Safety: Full mypy strict mode support
- Modern Tooling: uv package manager integration
- Automated Testing: pytest with comprehensive coverage
- CI/CD Pipeline: Multi-stage validation and quality gates

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Entry Points                              │
│                                                                     │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐      │
│   │     CLI      │    │   HTTP API   │    │ GitHub Webhooks  │      │
│   │  (agdd.cli)  │    │  (agdd.api)  │    │  (integrations)  │      │
│   └──────┬───────┘    └───────┬──────┘    └──────────┬───────┘      │
└──────────┼────────────────────┼──────────────────────┼──────────────┘
           │                    │                      │
           └────────────────────┼──────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Orchestration & Execution                        │
│                                                                     │
│   ┌─────────────────────────┐         ┌─────────────────────────┐   │
│   │    Agent Runner         │         │    Flow Runner          │   │
│   │  (MAG/SAG Orchestration)│◀────────│  (Optional Plugin)      │   │
│   │   - invoke_mag()        │         │   - flowctl adapter     │   │
│   │   - invoke_sag()        │         │   - dry-run support     │   │
│   │   - delegation          │         │                         │   │
│   └──────────┬──────────────┘         └─────────────────────────┘   │
└──────────────┼──────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Security & Moderation                           │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │  Content Moderation (omni-moderation-latest)                │   │
│   │   - Input/Output safety checks                              │   │
│   │   - Fail-closed/Fail-open strategies                        │   │
│   │   - Multimodal content support                              │   │
│   └─────────────────────────────────────────────────────────────┘   │
└──────────────┼──────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Core Components                              │
│                                                                     │
│   ┌─────────────┐     ┌──────────────┐     ┌──────────────────┐     │
│   │  Registry   │────▶│   Skills     │     │   Contracts      │     │
│   │  - agents   │     │  - reusable  │     │  - JSON Schema   │     │
│   │  - skills   │     │  - composable│     │  - validation    │     │
│   │  - routing  │     │              │     │                  │     │
│   └─────────────┘     └──────────────┘     └──────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Routing & Optimization Layer                      │
│                                                                     │
│  ┌─────────────┐  ┌───────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │ Router      │  │ Semantic Cache│  │ Batch Manager│  │ Cost     │ │
│  │ - SLA-based │  │ - FAISS/Redis │  │ - OpenAI     │  │ Optimizer│ │
│  │ - Auto-opt  │  │ - Vector K-NN │  │   Batch API  │  │ - Model  │ │
│  │ - Fallback  │  │ - 100% savings│  │ - 50% savings│  │   tiering│ │
│  └─────────────┘  └───────────────┘  └──────────────┘  └──────────┘ │
└──────────────┼──────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Multi-Provider Support                           │
│                                                                     │
│   ┌────────────┐   ┌───────────┐   ┌─────────┐   ┌────────────────┐ │
│   │  OpenAI    │   │ Anthropic │   │ Google  │   │ Local (Ollama) │ │
│   │ - Responses│   │ - Claude  │   │ - Gemini│   │ - Responses API│ │
│   │  API       │   │   3.5/Opus│   │   Pro   │   │   w/ fallback  │ │
│   │ - Batch    │   │           │   │         │   │                │ │
│   └────────────┘   └───────────┘   └─────────┘   └────────────────┘ │
└──────────────┼──────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Storage & Observability Layer                     │
│                                                                     │
│   ┌──────────────────────┐              ┌────────────────────────┐  │
│   │   Storage Layer      │              │   Observability        │  │
│   │  - SQLite (default)  │              │  - OpenTelemetry       │  │
│   │  - PostgreSQL/       │              │    + Langfuse          │  │
│   │    TimescaleDB       │              │  - Cost tracking       │  │
│   │  - Event envelope    │              │    (JSONL + SQLite)    │  │
│   │  - FTS5 search       │              │  - Distributed traces  │  │
│   └──────────┬───────────┘              └───────────┬────────────┘  │
└──────────────┼──────────────────────────────────────┼───────────────┘
               │                                      │
               └──────────────────┬───────────────────┘
                                  ▼
               ┌─────────────────────────────────────┐
               │       Governance Layer              │
               │                                     │
               │   ┌─────────────────────────────┐   │
               │   │    Governance Gate          │   │
               │   │  - Policy enforcement       │   │
               │   │  - Quality thresholds       │   │
               │   │  - Compliance checks        │   │
               │   └─────────────────────────────┘   │
               └─────────────────────────────────────┘
```

## Project Structure

```
agdd/
├── src/                        # Source code (Python src/ layout)
│   └── agdd/                   # Core Python package
│       ├── cli.py              # CLI entry point
│       ├── api/                # HTTP API (FastAPI)
│       ├── observability/      # Observability utilities
│       ├── registry.py         # Agent/skill resolution
│       ├── runners/            # Execution engines
│       ├── governance/         # Policy enforcement
│       ├── storage/            # Data persistence layer
│       └── assets/             # Bundled resources
├── catalog/                    # User-editable assets
│   ├── agents/                 # Agent implementations
│   │   ├── _template/          # MAG/SAG templates
│   │   ├── main/               # Main Agents (MAG)
│   │   └── sub/                # Sub-Agents (SAG)
│   ├── skills/                 # Reusable skill implementations
│   ├── contracts/              # JSON Schema contracts
│   ├── policies/               # Governance policies
│   ├── routing/                # Routing policies
│   ├── evals/                  # Evaluation configurations
│   └── registry/               # Configuration (agents.yaml, skills.yaml)
├── docs/                       # Documentation
│   ├── guides/                 # User guides
│   ├── reference/              # Reference docs
│   ├── development/            # Developer docs
│   └── policies/               # Project policies
├── ops/                        # Operational assets
│   ├── ci/                     # CI scripts
│   ├── scripts/                # Automation scripts
│   └── tools/                  # Development utilities
├── examples/                   # Example configurations
└── tests/                      # Test suite
```

## Quick Start

### Prerequisites

- Python 3.12+
- uv package manager ([Installation Guide](https://docs.astral.sh/uv/))

### Installation

```bash
git clone https://github.com/artificial-intelligence-first/agdd.git
cd agdd
cp .env.example .env  # customize API credentials and rate limits

# Minimal installation (core dependencies only)
uv sync

# Development installation (recommended - includes testing, linting, type checking)
uv sync --extra dev

# Verify installation
uv run -m pytest -q
```

#### Optional Features

Install additional features as needed:

```bash
# Semantic cache with FAISS (vector similarity search)
uv sync --extra cache --extra faiss

# Distributed rate limiting and Redis-backed cache
uv sync --extra redis

# PostgreSQL/TimescaleDB storage backend (production deployments)
uv sync --extra postgres

# Google AI provider (Gemini models)
uv sync --extra google

# Observability with OpenTelemetry and Langfuse
uv sync --extra observability

# MCP server support (expose agents to Claude Desktop)
uv sync --extra mcp-server

# Full installation (all optional features)
uv sync --extra dev --extra cache --extra faiss --extra redis --extra postgres --extra google --extra observability --extra mcp-server
```

**When to use each extra:**
- `dev`: Required for development, testing, and code quality checks
- `cache`: Required for semantic caching (provides numpy for embeddings)
- `faiss`: Required for FAISS-based vector similarity search (local semantic cache)
- `mcp-server`: Required to expose AGDD agents as MCP tools for Claude Desktop
- `redis`: Required for distributed rate limiting and Redis-based vector cache
- `postgres`: Required for PostgreSQL/TimescaleDB storage backend (production deployments)
- `google`: Required for Google Gemini provider (google-generativeai and google-genai)
- `observability`: Required for distributed tracing with OpenTelemetry and Langfuse integration

### Basic Usage

```bash
# Execute a MAG (Main Agent) with a candidate profile
echo '{"role":"Senior Engineer","level":"Senior","experience_years":8}' | \
  uv run agdd agent run offer-orchestrator-mag

# Or from a file
uv run agdd agent run offer-orchestrator-mag \
  --json examples/agents/candidate_profile.json
```

## Creating New Agents

AGDD provides templates for quickly creating new MAG and SAG agents:

### Using Agent Templates

```bash
# Copy MAG template
cp -r catalog/agents/_template/mag-template catalog/agents/main/your-orchestrator-mag

# Copy SAG template
cp -r catalog/agents/_template/sag-template catalog/agents/sub/your-advisor-sag

# Customize the templates:
# 1. Edit agent.yaml (slug, name, description, contracts)
# 2. Update README.md with your agent's purpose
# 3. Customize PERSONA.md with your agent's personality and behavior
# 4. Modify code/orchestrator.py (MAG) or code/advisor.py (SAG)
# 5. Create contract schemas in catalog/contracts/
# 6. Add tests in tests/agents/
```

### Using Make Commands

```bash
# Common development tasks
make test              # Run all tests
make test-agents       # Run agent tests only
make agent-run         # Execute sample MAG
make docs-check        # Validate documentation

# Flow Runner setup (optional)
make setup-flowrunner  # One-time setup
make flow-run          # Execute sample flow

# See all available targets
make help
```

## Agent Personas

AGDD supports **optional** persona configuration for agents via `PERSONA.md` files. Personas define an agent's personality, tone, behavioral guidelines, and response patterns.

### Persona File Structure

Each agent directory can include a `PERSONA.md` file:

```
catalog/agents/{role}/{slug}/
├── agent.yaml
├── README.md
├── PERSONA.md          ← Optional persona configuration
└── code/
```

### What's in a Persona?

A persona typically includes:

- **Personality**: Core traits (professional, concise, analytical, etc.)
- **Tone & Style**: Formality level, technical jargon usage, empathy level
- **Behavioral Guidelines**: How to handle uncertainty, provide information, communicate
- **Response Patterns**: Do's and don'ts, example interactions
- **Task-Specific Guidance**: Domain-specific instructions and best practices

### Example Persona Sections

```markdown
# Agent Persona

## Personality
Professional, concise, and action-oriented

## Tone & Style
- **Formality**: Formal and professional
- **Technical Jargon**: Medium level
- **Empathy**: Medium

## Behavioral Guidelines

### When Uncertain
- Always ask for clarification
- State what information is missing

### DO ✓
- Provide clear, actionable steps
- Use structured formats

### DON'T ✗
- Use hedging language
- Make unsubstantiated claims
```

### Using Personas in Agents

Personas are automatically loaded by the Registry. Agents can access and use persona content in LLM calls:

```python
from agdd.persona import build_system_prompt_with_persona, get_agent_persona

def run(payload, *, registry, skills, runner, obs):
    """Agent implementation with persona integration"""

    # Option 1: Get persona for current agent
    persona = get_agent_persona("my-agent-slug", registry=registry)

    # Option 2: Load agent and access persona directly
    agent = registry.load_agent("my-agent-slug")
    persona = agent.persona_content

    # Build system prompt with persona
    if persona:
        system_prompt = build_system_prompt_with_persona(
            base_prompt="Analyze the candidate profile and generate recommendations.",
            persona_content=persona
        )
    else:
        system_prompt = "Analyze the candidate profile and generate recommendations."

    # Use in LLM call (example with hypothetical LLM provider)
    # response = llm.generate(
    #     system=system_prompt,
    #     prompt=user_message
    # )

    return {"result": "..."}
```

**Helper Functions:**
- `build_system_prompt_with_persona()` - Combine persona with task instructions
- `get_agent_persona()` - Retrieve persona content by agent slug
- `extract_persona_section()` - Extract specific sections (e.g., "Behavioral Guidelines")

See `src/agdd/persona.py` for full API documentation.

### Templates

All agent templates (`_template/mag-template`, `_template/sag-template`, etc.) include starter `PERSONA.md` files with comprehensive examples. Use these as a starting point and customize for your specific agent's domain and behavior requirements.

See existing agents (`offer-orchestrator-mag`, `compensation-advisor-sag`) for real-world examples.

## Usage

### Agent Orchestration

```bash
# Execute MAG (Main Agent)
echo '{"role":"Senior Engineer","level":"Senior","experience_years":8}' | \
  uv run agdd agent run offer-orchestrator-mag

# From file
uv run agdd agent run offer-orchestrator-mag \
  --json examples/agents/candidate_profile.json
```

Observability artifacts are generated in `.runs/agents/<RUN_ID>/`.
Cost trackers persist JSONL and SQLite artifacts under `.runs/costs/`.

### HTTP API

The FastAPI server exposes agent orchestration over HTTP with authentication, rate limiting, and real-time log streaming.

```bash
# Start with defaults (0.0.0.0:8000, /api/v1 prefix)
uv run uvicorn agdd.api.server:app --host 0.0.0.0 --port 8000

# Development hot-reload with debug logging
AGDD_API_DEBUG=1 uv run uvicorn agdd.api.server:app --reload

# Override configuration via environment variables
AGDD_API_KEY="local-dev-key" \
AGDD_RATE_LIMIT_QPS=5 \
AGDD_GITHUB_WEBHOOK_SECRET="change-me" \
uv run uvicorn agdd.api.server:app
```

Quick commands once the server is running:

```bash
# List available agents
curl -H "Authorization: Bearer $AGDD_API_KEY" \
  http://localhost:8000/api/v1/agents | jq

# Execute a main agent
curl -X POST \
  -H "Authorization: Bearer $AGDD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"payload": {"role":"Senior Engineer","level":"Senior","experience_years":8}}' \
  http://localhost:8000/api/v1/agents/offer-orchestrator-mag/run | jq

# Retrieve run summary and latest logs
curl -H "Authorization: Bearer $AGDD_API_KEY" \
  http://localhost:8000/api/v1/runs/<RUN_ID> | jq
curl -H "Authorization: Bearer $AGDD_API_KEY" \
  "http://localhost:8000/api/v1/runs/<RUN_ID>/logs?tail=20"

# Follow logs with SSE (requires curl -N to keep the connection open)
curl -N -H "Authorization: Bearer $AGDD_API_KEY" \
  "http://localhost:8000/api/v1/runs/<RUN_ID>/logs?follow=true"
```

Interactive documentation is available at:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- OpenAPI schema: <http://localhost:8000/api/v1/openapi.json>

See [api-usage.md](./docs/guides/api-usage.md) for a complete endpoint reference, authentication details, and troubleshooting tips. Additional curl examples are provided in [`examples/api/curl_examples.sh`](./examples/api/curl_examples.sh).

### GitHub Integration

The GitHub webhook bridge triggers agents from comments and posts the results back to pull requests or issues.

- Supported events: `issue_comment`, `pull_request_review_comment`, and `pull_request`
- Command syntax: `@agent-slug {"json": "payload"}`
- Responses include run IDs and links back to the HTTP API for logs and summaries

Provision the webhook with the helper script:

```bash
GITHUB_WEBHOOK_SECRET=my-secret \
./ops/scripts/setup-github-webhook.sh owner/repo https://api.example.com/api/v1/github/webhook
```

Ensure the API server has `AGDD_GITHUB_WEBHOOK_SECRET` (for signature verification) and `AGDD_GITHUB_TOKEN` (for posting comments). Full setup instructions, comment examples, and GitHub Actions workflows live in [github-integration.md](./docs/guides/github-integration.md).

### Flow Runner

```bash
# Check availability
uv run agdd flow available

# Validate flow
uv run agdd flow validate examples/flowrunner/prompt_flow.yaml

# Execute flow
uv run agdd flow run examples/flowrunner/prompt_flow.yaml
```

### Observability

```bash
# Generate summary
uv run agdd flow summarize

# Custom directory
uv run agdd flow summarize --base /path/to/.runs

# Output to file
uv run agdd flow summarize --output flow_summary.json
```

Summary metrics include execution stats, errors, MCP calls, per-step performance, and per-model resource usage.
Detailed cost data is appended to `.runs/costs/costs.jsonl` and aggregated in `.runs/costs.db`. The summarizer is backed by `src/agdd/observability/summarize_runs.py`.

### Data Management (New Storage Layer)

AGDD includes a pluggable storage layer for querying and analyzing agent execution data:

```bash
# Initialize storage (SQLite by default)
uv run agdd data init

# Query runs
uv run agdd data query --agent offer-orchestrator-mag --limit 20
uv run agdd data query --run-id mag-a1b2c3d4

# Full-text search across events (requires FTS5)
uv run agdd data search "error rate limit"

# Clean up old data
uv run agdd data vacuum --hot-days 7 --dry-run
uv run agdd data vacuum --hot-days 7
```

**Key Features:**
- **SQLite backend** (default): Zero-config local storage with FTS5 full-text search
- **PostgreSQL/TimescaleDB backend** (beta): Production-grade storage via `asyncpg` (enable with `pip install agdd[postgres]`)
- **Event envelope pattern**: Strongly-typed common fields + flexible JSON payloads
- **Migration tool**: Import legacy `.runs/agents/` data for analysis while new cost tracking lives in `.runs/costs/`

**Note**: The storage layer is for data management/analysis. Agent developers continue using `ObservabilityLogger` (see [agent-development.md](./docs/guides/agent-development.md)).

See [docs/storage.md](./docs/storage.md) for complete documentation.

### Governance

```bash
# Enforce quality thresholds
uv run agdd flow gate flow_summary.json \
  --policy catalog/policies/flow_governance.yaml
```


## Documentation

### Core Guides
- [docs/guides/agent-development.md](./docs/guides/agent-development.md) - Development playbook and workflow guide
- [docs/guides/api-usage.md](./docs/guides/api-usage.md) - HTTP API reference and authentication guide
- [docs/guides/runner-integration.md](./docs/guides/runner-integration.md) - Runner capabilities and integration
- [docs/guides/github-integration.md](./docs/guides/github-integration.md) - GitHub webhook integration guide

### Advanced Capabilities
- [docs/guides/multi-provider.md](./docs/guides/multi-provider.md) - Multi-provider LLM support and model selection
- [docs/guides/cost-optimization.md](./docs/guides/cost-optimization.md) - Cost tracking and optimization strategies
- [docs/guides/semantic-cache.md](./docs/guides/semantic-cache.md) - Semantic caching with vector similarity search
- [docs/guides/moderation.md](./docs/guides/moderation.md) - Content moderation with OpenAI omni-moderation
- [docs/guides/mcp-integration.md](./docs/guides/mcp-integration.md) - Model Context Protocol integration
- [docs/guides/a2a-communication.md](./docs/guides/a2a-communication.md) - Agent-to-Agent communication patterns (MAG/SAG)

### Reference
- [docs/storage.md](./docs/storage.md) - Storage layer and data management
- [docs/reference/ssot.md](./docs/reference/ssot.md) - Terminology and policies reference
- [docs/development/roadmap.md](./docs/development/roadmap.md) - Roadmap and execution plans
- [docs/development/changelog.md](./docs/development/changelog.md) - Version history

## Development

### Workflow

1. Review `docs/reference/ssot.md` for terminology and policies
2. Update `docs/development/roadmap.md` before making changes
3. Implement changes following `docs/guides/agent-development.md` guidelines
4. Run validation checks
5. Update `docs/development/changelog.md`
6. Submit pull request

### Validation

```bash
# Run tests
uv run -m pytest -q

# Check documentation
uv run python ops/tools/check_docs.py

# Verify vendor assets
uv run python ops/tools/verify_vendor.py
```

### Pre-commit Hooks

This project uses pre-commit hooks to ensure code quality:

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

Hooks run automatically on `git commit` and check:
- Ruff linting and formatting
- Type checking (mypy)
- YAML/JSON/TOML validation
- Trailing whitespace
- Private key detection

## Contributing

Contributions are welcome. Please refer to [agent-development.md](./docs/guides/agent-development.md) for the complete development workflow and PR policy.

### Requirements

- Pass all automated tests and validation checks
- Follow documentation standards
- Update relevant documentation files
- Record terminology changes in `docs/reference/ssot.md`
- Add tests for new features
- Update `docs/development/changelog.md`

### Code Quality

- Type Safety: Full mypy strict mode compliance
- Formatting: ruff for linting and formatting
- Testing: pytest with comprehensive coverage
- Documentation: Clear docstrings and updated guides

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

Copyright © 2025 Naru Kijima
