# AG-Driven Development (AGDD) Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

A comprehensive framework for AG-Driven Development (AGDD) systems. This repository provides the foundational infrastructure for orchestrating automated workflows through agent descriptors, skills, contracts, and CI guardrails.

## Overview

AGDD Framework enables developers to build and manage automated agent-driven workflows with built-in quality controls and observability. The system includes registry management, skill composition, contract verification, and comprehensive documentation standards.

## Features

- **Agent Registry**: Centralized management of agent descriptors and routing
- **Skills Framework**: Reusable, composable skills for agent capabilities
- **Contract Verification**: Automated validation of system contracts and invariants
- **Runner Plugins**: Pluggable runner boundary (Flow Runner provided by default)
- **Walking Skeleton CLI**: Typer-powered entry point that exercises registry -> contract -> skill execution
- **Documentation Standards**: Enforced documentation policies and guardrails
- **Observability**: Built-in monitoring and logging infrastructure
- **Packaged Schemas & Policies**: JSON Schemas and governance policies bundled for importlib-based loading
- **CI Integration**: GitHub Actions workflows for automated testing and validation

## Project Structure

```
.
|-- agdd/            # Core Python package (CLI, runners, governance, bundled assets)
|-- registry/        # Agent and skill registries plus per-agent descriptors
|-- contracts/       # JSON Schemas governing descriptors and flow summaries
|-- policies/        # Governance policies applied to summarized runs
|-- observability/   # Run summarization utilities
|-- examples/        # Sample flows and reference inputs
|-- tools/           # Development and validation tools
|-- tests/           # Pytest coverage for contracts, CLI, and tooling
`-- docs/            # Supporting documentation artefacts (if present)
```

## Getting Started

### Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) package manager

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd agdd
   ```

2. Install dependencies:
   ```bash
   uv sync
   ```

3. Install development extras (recommended for local testing):
   ```bash
   uv sync --extra dev
   ```

4. Verify installation:
   ```bash
   uv run -m pytest -q
   ```

5. Smoke test the walking skeleton:
   ```bash
   uv run python -m agdd.cli validate
   uv run python -m agdd.cli run hello --text "AGDD"
   ```

6. (Optional) Install Flow Runner to exercise the runner CLI:
   ```bash
   git clone https://github.com/artificial-intelligence-first/flow-runner.git
   cd flow-runner
   uv sync
   uv pip install -e packages/mcprouter -e packages/flowrunner
   cd ..
   source tools/flowrunner_env.sh  # exports FLOW_RUNNER_PYTHONPATH
   ```

## Usage

### Documentation Validation

Run documentation policy checks:
```bash
uv run python tools/check_docs.py
```

### Running Tests

Run the full test suite:
```bash
uv run -m pytest -q
```

### Vendor Integrity

Verify vendored Flow Runner assets (schema and example flow) match expected hashes:
```bash
uv run python tools/verify_vendor.py
```

### Walking Skeleton CLI

Execute the Typer CLI that exercises the AI-first pipeline:
```bash
uv run python -m agdd.cli validate
uv run python -m agdd.cli run hello --text "AGDD"
```

### Flow Runner CLI

The runner boundary exposes Flow Runner commands once `flowctl` is available:
```bash
uv run python -m agdd.cli flow available
uv run python -m agdd.cli flow validate examples/flowrunner/prompt_flow.yaml
uv run python -m agdd.cli flow run examples/flowrunner/prompt_flow.yaml --dry-run
uv run python -m agdd.cli flow run examples/flowrunner/prompt_flow.yaml  # produce .runs/ artifacts
```
`flow available` reports the detected runner version and capability set when the CLI is installed.

If you clone Flow Runner to a different location, set `export FLOW_RUNNER_DIR=/path/to/flow-runner` before sourcing the helper script.

Example flows live under `examples/flowrunner/` and the canonical schema is mirrored at `contracts/flow.schema.json` (tag `flowrunner-v1.0.0`).

### Observability

Flow Runner executions emit structured artifacts under `.runs/<RUN_ID>/`. Summaries can be generated with:
```bash
uv run python -m agdd.cli flow summarize
```
Or target a custom directory:
```bash
uv run python -m agdd.cli flow summarize --base /path/to/.runs
uv run python -m agdd.cli flow summarize --output governance/flow_summary.json
```

The generated summary includes:
- `runs` / `successes` / `success_rate`
- `avg_latency_ms`
- `errors` (total failures and error-type breakdown)
- `mcp` (calls, errors, aggregated tokens, cost)
- `steps` (per-step run count, success rate, average latency, optional model and error data)
- `models` (per-model calls, errors, tokens, cost)

The optional `--output` flag writes the JSON payload to disk, enabling downstream governance tooling (e.g., Multi Agent Governance workflows) to consume the metrics. Governance thresholds are defined in `policies/flow_governance.yaml` and enforced via:
```bash
uv run python -m agdd.cli flow gate governance/flow_summary.json --policy policies/flow_governance.yaml
```
The summary contract is captured in `contracts/flow_summary.schema.json`, and CI publishes the generated summary artifact alongside test results.

### Packaged Resources

The CLI depends on JSON Schemas and governance policies distributed within the `agdd` wheel under `agdd/assets/`. Building the project ensures these files ship with the package so `importlib.resources` can resolve them:
```bash
uv build
python -m venv .venv_pkgtest
.venv_pkgtest/bin/pip install dist/agdd-*.whl
.venv_pkgtest/bin/agdd validate
```
Use a disposable virtual environment for this smoke test and delete it afterwards.

## Documentation

- **[AGENTS.md](./AGENTS.md)**: Local development playbook and workflow guide
- **[SSOT.md](./SSOT.md)**: Single source of truth for terminology and policies
- **[PLANS.md](./PLANS.md)**: Execution plans and roadmap
- **[CHANGELOG.md](./CHANGELOG.md)**: Version history and updates
- **[RUNNERS.md](./RUNNERS.md)**: Runner capabilities, conformance, and swap guidance

## Development Workflow

1. Review `SSOT.md` for terminology and policies
2. Update `PLANS.md` before making changes
3. Smoke test the walking skeleton (`agdd.cli validate` / `run`) as part of development
4. Make your changes following the guidelines in `AGENTS.md`
5. Run validation tools and tests
6. Update `CHANGELOG.md` upon completion
7. Submit a pull request

## Contributing

Please refer to `AGENTS.md` for the complete development workflow and PR policy. All contributions should:

- Pass all automated tests and validation checks
- Follow documentation standards
- Update relevant documentation files
- Record terminology changes in `SSOT.md`

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

Copyright (c) 2025 Naru Kijima
