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
- [HTTP API](#http-api)
- [GitHub Integration](#github-integration)
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

### Advanced Capabilities
- Runner Plugins: Pluggable execution engines (Flow Runner included)
- MAG/SAG Architecture: Main and Sub-Agent orchestration patterns
- Observability: Comprehensive metrics, traces, and cost tracking
- Governance Gates: Policy-based validation and compliance checks

### Developer Experience
- Type Safety: Full mypy strict mode support
- Modern Tooling: uv package manager integration
- Automated Testing: pytest with comprehensive coverage
- CI/CD Pipeline: Multi-stage validation and quality gates

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                          CLI Layer                          │
│                         (agdd.cli)                          │
└────────────┬────────────────────────────┬───────────────────┘
             │                            │
             ▼                            ▼
┌────────────────────────┐   ┌───────────────────────────────┐
│   Execution Layer      │   │      Core Components          │
│                        │   │                               │
│  ┌──────────────────┐  │   │  ┌─────────┐  ┌───────────┐   │
│  │  Agent Runner    │──┼───┼─▶│ Skills  │  │ Contracts │   │
│  └──────────────────┘  │   │  └─────────┘  └───────────┘   │
│                        │   │       ▲            ▲          │
│  ┌──────────────────┐  │   │       │            │          │
│  │  Flow Runner     │  │   │  ┌────┴────────────┘───────┐  │
│  └────────┬─────────┘  │   │  │       Registry          │  │
│           │            │   │  └─────────────────────────┘  │
└───────────┼────────────┘   └───────────────────────────────┘
            ▼
┌───────────────────────┐
│  Governance Layer     │
│                       │
│  ┌─────────────────┐  │
│  │ Observability   │  │
│  └────────┬────────┘  │
│           ▼           │
│  ┌─────────────────┐  │
│  │ Governance Gate │  │
│  └─────────────────┘  │
└───────────────────────┘
```

## Project Structure

```
agdd/
├── agdd/                       # Core Python package
│   ├── cli.py                  # CLI entry point
│   ├── api/                    # HTTP API (FastAPI)
│   ├── registry.py             # Agent/skill resolution
│   ├── runners/                # Execution engines
│   ├── governance/             # Policy enforcement
│   └── assets/                 # Bundled resources
├── agents/                     # Agent implementations
│   ├── _template/              # MAG/SAG templates
│   ├── main/                   # Main Agents (MAG)
│   └── sub/                    # Sub-Agents (SAG)
├── skills/                     # Reusable skill implementations
├── registry/                   # Configuration
│   ├── agents.yaml             # Task routing
│   └── skills.yaml             # Skill definitions
├── contracts/                  # JSON Schemas
├── policies/                   # Governance policies
├── scripts/                    # Automation scripts
├── tools/                      # Development utilities
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
uv sync
uv sync --extra dev  # for development
# Optional: seed environment configuration (edit the new .env file before running the server)
cp .env.example .env
uv run -m pytest -q  # verify installation
```

### Basic Usage

```bash
# Execute a MAG (Main Agent) with a candidate profile
echo '{"role":"Senior Engineer","level":"Senior","experience_years":8}' | \
  uv run agdd agent run offer-orchestrator-mag

# Or from a file
uv run agdd agent run offer-orchestrator-mag \
  --json examples/agents/candidate_profile.json
```

## HTTP API

The FastAPI-powered HTTP surface turns the AGDD agent runtime into a network service.

### Highlights

- JSON-over-HTTP endpoints for listing agents, launching executions, and retrieving artifacts
- Built-in bearer token authentication and optional GitHub webhook signature verification
- Rate limiting with in-memory and Redis backends
- Real-time log streaming via Server-Sent Events (SSE)
- Interactive OpenAPI docs available at `/docs` and `/redoc`

### Quick Start

```bash
# Ensure configuration is in place (API key, CORS, GitHub secrets, etc.)
cp .env.example .env
vim .env  # update values as needed

# Launch the server (hot reload in development)
uv run uvicorn agdd.api.server:app --host 0.0.0.0 --port 8000

# Verify health
curl -H "Authorization: Bearer $AGDD_API_KEY" http://localhost:8000/health

# List agents
curl -H "Authorization: Bearer $AGDD_API_KEY" http://localhost:8000/api/v1/agents | jq

# Execute an agent
curl -H "Authorization: Bearer $AGDD_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"payload": {"role": "Senior Engineer", "level": "Senior"}}' \
     http://localhost:8000/api/v1/agents/offer-orchestrator-mag/run | jq

# Retrieve observability artifacts
curl -H "Authorization: Bearer $AGDD_API_KEY" http://localhost:8000/api/v1/runs/<RUN_ID> | jq
curl -H "Authorization: Bearer $AGDD_API_KEY" http://localhost:8000/api/v1/runs/<RUN_ID>/logs?tail=20

# Stream logs live (SSE)
curl -N -H "Authorization: Bearer $AGDD_API_KEY" \
     "http://localhost:8000/api/v1/runs/<RUN_ID>/logs?follow=true"
```

> **Tip:** Enable distributed rate limiting by installing the optional Redis extra: `uv sync --extra redis`.

See [API.md](./API.md) for exhaustive request/response schemas, authentication guidance, and troubleshooting tips.

## GitHub Integration

GitHub webhooks allow teams to trigger agents directly from issues, pull requests, and review comments.

### Capabilities

- Comment syntax: `@agent-slug {"json": "payload"}` with multiline and code-block support
- Event coverage: `issue_comment`, `pull_request_review_comment`, and `pull_request`
- Automatic result comments containing run IDs, artifact links, and execution output
- Hardened HMAC SHA-256 signature verification and optional API authentication
- Helper script for provisioning webhooks via the GitHub CLI (`scripts/setup-github-webhook.sh`)

### Bootstrapping

```bash
# Configure secrets in your API environment
export AGDD_GITHUB_WEBHOOK_SECRET=super-secret
export AGDD_GITHUB_TOKEN=ghp_xxx  # requires repo:write permissions

# Provision the webhook (requires gh CLI)
GITHUB_WEBHOOK_SECRET=$AGDD_GITHUB_WEBHOOK_SECRET \
  ./scripts/setup-github-webhook.sh owner/repo https://your-api.example.com/api/v1/github/webhook

# Comment on an issue or PR
@offer-orchestrator-mag {
  "role": "Senior Engineer",
  "level": "Senior"
}

# The bot replies with run status, run_id, and links to observability endpoints
```

Detailed operational procedures live in [GITHUB.md](./GITHUB.md), including troubleshooting guidance and GitHub Actions examples.

## Creating New Agents

AGDD provides templates for quickly creating new MAG and SAG agents:

### Using Agent Templates

```bash
# Copy MAG template
cp -r agents/_template/mag-template agents/main/your-orchestrator-mag

# Copy SAG template
cp -r agents/_template/sag-template agents/sub/your-advisor-sag

# Customize the templates:
# 1. Edit agent.yaml (slug, name, description, contracts)
# 2. Update README.md with your agent's purpose
# 3. Modify code/orchestrator.py (MAG) or code/advisor.py (SAG)
# 4. Create contract schemas in contracts/
# 5. Add tests in tests/agents/
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

### HTTP API

The HTTP interface is documented in detail in the [HTTP API](#http-api) section and [API.md](./API.md).
Run `./examples/api/curl_examples.sh` for an end-to-end demo that exercises every endpoint
including SSE log streaming.

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

### Governance

```bash
# Enforce quality thresholds
uv run agdd flow gate flow_summary.json \
  --policy policies/flow_governance.yaml
```


## Documentation

- [AGENTS.md](./AGENTS.md) - Development playbook and workflow guide
- [API.md](./API.md) - HTTP API reference and authentication guide
- [GITHUB.md](./GITHUB.md) - GitHub webhook integration manual
- [SSOT.md](./SSOT.md) - Terminology and policies reference
- [PLANS.md](./PLANS.md) - Roadmap and execution plans
- [RUNNERS.md](./RUNNERS.md) - Runner capabilities and integration
- [CHANGELOG.md](./CHANGELOG.md) - Version history

## Development

### Workflow

1. Review `SSOT.md` for terminology and policies
2. Update `PLANS.md` before making changes
3. Implement changes following `AGENTS.md` guidelines
4. Run validation checks
5. Update `CHANGELOG.md`
6. Submit pull request

### Validation

```bash
# Run tests
uv run -m pytest -q

# Check documentation
uv run python tools/check_docs.py

# Verify vendor assets
uv run python tools/verify_vendor.py
```

## Contributing

Contributions are welcome. Please refer to [AGENTS.md](./AGENTS.md) for the complete development workflow and PR policy.

### Requirements

- Pass all automated tests and validation checks
- Follow documentation standards
- Update relevant documentation files
- Record terminology changes in `SSOT.md`
- Add tests for new features
- Update `CHANGELOG.md`

### Code Quality

- Type Safety: Full mypy strict mode compliance
- Formatting: ruff for linting and formatting
- Testing: pytest with comprehensive coverage
- Documentation: Clear docstrings and updated guides

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

Copyright © 2025 Naru Kijima
