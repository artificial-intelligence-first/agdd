# AG-Driven Development (AGDD) Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

A comprehensive framework for AG-Driven Development (AGDD) systems. This repository provides the foundational infrastructure for orchestrating automated workflows through agent descriptors, skills, contracts, and CI guardrails.

## Overview

AGDD Framework enables developers to build and manage automated agent-driven workflows with built-in quality controls and observability. The system includes registry management, skill composition, contract verification, and comprehensive documentation standards.

## Features

- **Agent Registry**: Centralized management of agent descriptors and routing
- **Skills Framework**: Reusable, composable skills for agent capabilities
- **Contract Verification**: Automated validation of system contracts and invariants
- **Documentation Standards**: Enforced documentation policies and guardrails
- **Observability**: Built-in monitoring and logging infrastructure
- **CI Integration**: GitHub Actions workflows for automated testing and validation

## Project Structure

```
agdd/
├── agents/          # Agent descriptors and routing configurations
├── skills/          # Reusable agent skills
├── contracts/       # System contracts and validation logic
├── registry/        # Central registry for agents and skills
├── policies/        # Policy definitions and enforcement
├── ci/              # CI/CD configurations
├── observability/   # Monitoring and logging setup
├── tools/           # Development and validation tools
└── tests/           # Test suite
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

3. Verify installation:
   ```bash
   uv run -m pytest -q
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

## Documentation

- **[AGENTS.md](./AGENTS.md)**: Local development playbook and workflow guide
- **[SSOT.md](./SSOT.md)**: Single source of truth for terminology and policies
- **[PLANS.md](./PLANS.md)**: Execution plans and roadmap
- **[CHANGELOG.md](./CHANGELOG.md)**: Version history and updates

## Development Workflow

1. Review `SSOT.md` for terminology and policies
2. Update `PLANS.md` before making changes
3. Make your changes following the guidelines in `AGENTS.md`
4. Run validation tools and tests
5. Update `CHANGELOG.md` upon completion
6. Submit a pull request

## Contributing

Please refer to `AGENTS.md` for the complete development workflow and PR policy. All contributions should:

- Pass all automated tests and validation checks
- Follow documentation standards
- Update relevant documentation files
- Record terminology changes in `SSOT.md`

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

Copyright (c) 2025 Naru Kijima (黄島成)
