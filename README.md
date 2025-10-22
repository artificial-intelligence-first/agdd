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
- [Configuration](#configuration)
- [HTTP API](#http-api)
- [GitHub Integration](#github-integration)
- [Project Structure](#project-structure)
- [Usage](#usage)
- [Documentation](#documentation)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

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

## Configuration

- Copy [`.env.example`](./.env.example) to `.env` to enable local overrides.
- The most commonly tuned variables are:
  - `AGDD_API_HOST` / `AGDD_API_PORT` – bind address for the HTTP API server.
  - `AGDD_API_KEY` – bearer or `x-api-key` token required for all HTTP API requests in production.
  - `AGDD_RATE_LIMIT_QPS` and `AGDD_REDIS_URL` – enable in-memory or Redis-backed rate limiting.
  - `AGDD_GITHUB_WEBHOOK_SECRET` and `AGDD_GITHUB_TOKEN` – secure GitHub webhook processing and comment replies.
  - `AGDD_CORS_ORIGINS` – JSON array of allowed origins for browser clients.
- Install optional extras with `uv sync --extra redis` when enabling Redis-backed rate limiting.
- Environment variables are parsed by Pydantic settings; restart the API server after making changes.

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

## HTTP API

The AGDD HTTP API exposes the same orchestration capabilities as the CLI with a FastAPI service.

### Quick Start

```bash
# 1. Configure environment variables (optional)
cp .env.example .env

# 2. Launch the server (reload honours AGDD_API_DEBUG=true)
./scripts/run-api-server.sh

# 3. Authenticate requests (Bearer token or x-api-key header)
export AGDD_API_KEY="<your-api-key>"
```

### Core Endpoints

All endpoints live under `/api/v1` by default. Replace `localhost:8000` with your deployment host.

```bash
# List registered agents
curl -sS -H "Authorization: Bearer $AGDD_API_KEY" \
  http://localhost:8000/api/v1/agents | jq '.'

# Execute an agent with a JSON payload
curl -sS -X POST \
  -H "Authorization: Bearer $AGDD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"payload": {"role": "Senior Engineer", "level": "Senior"}}' \
  http://localhost:8000/api/v1/agents/offer-orchestrator-mag/run | jq '.'

# Fetch run summary and metrics
curl -sS -H "Authorization: Bearer $AGDD_API_KEY" \
  http://localhost:8000/api/v1/runs/<RUN_ID> | jq '.'

# Tail the last 20 log lines (NDJSON)
curl -sS -H "Authorization: Bearer $AGDD_API_KEY" \
  "http://localhost:8000/api/v1/runs/<RUN_ID>/logs?tail=20"

# Stream live logs via Server-Sent Events (Ctrl+C to stop)
curl -N -H "Authorization: Bearer $AGDD_API_KEY" \
  "http://localhost:8000/api/v1/runs/<RUN_ID>/logs?follow=true"
```

Interactive documentation is available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI schema: `http://localhost:8000/api/v1/openapi.json`

See [API.md](./API.md) for complete request/response reference, authentication guidance, and rate limiting configuration. Additional ready-to-run examples live in [`examples/api/curl_examples.sh`](./examples/api/curl_examples.sh).

## GitHub Integration

GitHub comments, reviews, and pull request bodies can trigger AGDD agents automatically.

### Supported Events

- Issue comments (`issue_comment`)
- Pull request review comments (`pull_request_review_comment`)
- Pull request body updates (`pull_request` – opened, edited, synchronize)

### Comment Syntax

```
@offer-orchestrator-mag {
  "role": "Staff Engineer",
  "level": "Staff",
  "experience_years": 12
}
```

- Multiple commands per comment are supported, including inside `\`\`\`json` code fences.
- Payloads must be valid JSON objects; malformed payloads are ignored.

### Setup Checklist

1. Deploy the HTTP API with `AGDD_GITHUB_WEBHOOK_SECRET` and `AGDD_GITHUB_TOKEN` configured.
2. Register the webhook: `GITHUB_WEBHOOK_SECRET=... ./scripts/setup-github-webhook.sh owner/repo https://api.example.com/api/v1/github/webhook`.
3. Grant the GitHub token permission to read and write issues and pull requests.
4. Test by posting a comment that mentions an agent slug.

Successful runs post a ✅ comment containing the `run_id` and API artifact links. Failures emit troubleshooting tips and the exception details. Signature verification is enforced whenever a webhook secret is set.

Refer to [GITHUB.md](./GITHUB.md) for full workflow diagrams, troubleshooting guidance, and [examples/api/github_actions.yml](./examples/api/github_actions.yml) for GitHub Actions automation patterns.

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
- [API.md](./API.md) - Endpoint reference, authentication, and rate limiting
- [GITHUB.md](./GITHUB.md) - Webhook setup, comment syntax, and troubleshooting
- [SSOT.md](./SSOT.md) - Terminology and policies reference
- [PLANS.md](./PLANS.md) - Roadmap and execution plans
- [RUNNERS.md](./RUNNERS.md) - Runner capabilities and integration
- [CHANGELOG.md](./CHANGELOG.md) - Version history
- [.env.example](./.env.example) - Documented environment defaults for the API server

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
