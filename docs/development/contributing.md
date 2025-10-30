---
title: Contributing to AGDD
last_synced: 2025-10-24
description: Contribution guidelines, development setup, and PR process
change_log:
  - 2025-10-24: Added front-matter and structured contribution guidelines
---

# Contributing to AGDD

Thank you for your interest in contributing to the AG-Driven Development (AGDD) framework!

## Project Status

**This project is primarily maintained for internal use within our organization, but we welcome external contributions.**

While the core development roadmap is driven by internal needs, we value community feedback, bug reports, and contributions that align with the project's goals.

## Development Setup

### Prerequisites

- **Python 3.12+** (required)
- **uv package manager** ([Installation Guide](https://docs.astral.sh/uv/))

### Initial Setup

```bash
# Clone the repository
git clone https://github.com/artificial-intelligence-first/agdd.git
cd agdd

# Copy environment template
cp .env.example .env
# Edit .env to add your API credentials if needed

# Install dependencies
uv sync

# Install development dependencies (recommended)
uv sync --extra dev

# Verify installation
uv run -m pytest -q
```

## Development Workflow

### 1. Fork and Create a Branch

```bash
# Fork the repository on GitHub first, then:
git clone https://github.com/YOUR_USERNAME/agdd.git
cd agdd
git remote add upstream https://github.com/artificial-intelligence-first/agdd.git

# Create a feature branch
git checkout -b feature/your-feature-name
```

### 2. Make Your Changes

- Follow the code standards outlined below
- Write or update tests as needed
- Update documentation to reflect your changes
- Run validation checks locally before committing

### 3. Testing Requirements

All contributions must include appropriate tests and maintain existing test coverage.

```bash
# Run the full test suite
uv run -m pytest

# Run with coverage report
uv run -m pytest --cov=agdd --cov-report=term-missing

# Run specific test categories
uv run -m pytest tests/unit/           # Unit tests only
uv run -m pytest tests/agents/         # Agent tests only
uv run -m pytest tests/integration/    # Integration tests only

# Or use the Makefile
make test
make test-agents
```

**Coverage Requirements:**
- Maintain or improve overall test coverage
- New features must include unit tests
- Bug fixes should include regression tests
- Integration tests for API/agent changes

### 4. Code Quality Checks

Run all quality checks before submitting your PR:

```bash
# Linting and formatting (ruff)
uv run ruff check .
uv run ruff format .

# Type checking (mypy strict mode)
uv run mypy src tests

# Documentation validation
uv run python ops/tools/check_docs.py

# Or use the Makefile
make lint
make type-check
make docs-check
```

### 5. Update CHANGELOG.md

Add your changes to the `[Unreleased]` section of `CHANGELOG.md`:

```markdown
## [Unreleased]
### Added
- Your new feature description

### Changed
- Your modification description

### Fixed
- Your bug fix description
```

Follow the [Keep a Changelog](https://keepachangelog.com/) format.

### 6. Commit Your Changes

We follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages:

```bash
# Format: <type>(<scope>): <description>

git commit -m "feat(api): add webhook retry mechanism"
git commit -m "fix(agents): correct contract validation logic"
git commit -m "docs: update API authentication guide"
git commit -m "test: add integration tests for storage layer"
```

**Commit Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Test additions or modifications
- `refactor`: Code refactoring without behavior changes
- `perf`: Performance improvements
- `chore`: Maintenance tasks, dependency updates

### 7. Push and Create Pull Request

```bash
# Push to your fork
git push origin feature/your-feature-name

# Create a pull request on GitHub
# Provide a clear title and description following our PR template
```

## Code Standards

### Python Code Style

- **Line Length:** 100 characters maximum (configured in `pyproject.toml`)
- **Formatting:** Use `ruff format` for automatic formatting
- **Linting:** Use `ruff check` and fix all warnings
- **Type Hints:** Full type annotations required (mypy strict mode)
- **Docstrings:** Use clear docstrings for public APIs

### Type Safety

All code must pass `mypy --strict` checks:

```bash
uv run mypy src tests
```

- Avoid `Any` types where possible
- Provide complete type annotations for functions and methods
- Use generics and protocols appropriately
- No implicit `Optional` types

### Testing Standards

- **Framework:** pytest with async support (`pytest-asyncio`)
- **Structure:** Organize tests by category (unit/agents/integration)
- **Fixtures:** Use fixtures for common setup
- **Assertions:** Clear, descriptive assertions
- **Mocking:** Use pytest fixtures and monkeypatch when needed

### Documentation Standards

- **README.md:** Keep quick start guide current
- **[AGENTS.md](../architecture/agents.md):** Update for agent development changes
- **API.md:** Document new API endpoints
- **[SSOT.md](../architecture/ssot.md):** Record new terminology or policy decisions
- **[PLANS.md](../architecture/plans.md):** Update roadmap for significant features

## Pull Request Process

### Before Submitting

1. Ensure all tests pass locally
2. Run all code quality checks (ruff, mypy)
3. Update relevant documentation
4. Add entry to CHANGELOG.md under `[Unreleased]`
5. Rebase on latest main branch if needed

### PR Requirements

- **Title:** Use conventional commit format
- **Description:** Clear explanation of changes and motivation
- **Tests:** Include test results or coverage report
- **Documentation:** Note any documentation updates
- **Breaking Changes:** Clearly mark and justify any breaking changes

### Review Process

- PRs will be reviewed primarily by maintainers
- Address review feedback promptly
- Be open to suggestions and alternative approaches
- Squash commits before merging if requested

### CI Pipeline

All PRs must pass the CI pipeline:

- Core tests (pytest with coverage)
- Type checking (mypy strict)
- Linting (ruff)
- Documentation validation
- Flow Runner tests
- Agent orchestration tests

## What We're Looking For

### High-Priority Contributions

- Bug fixes with regression tests
- Performance improvements with benchmarks
- Documentation improvements and examples
- Test coverage improvements
- Security enhancements

### Lower-Priority Contributions

- Major feature additions (discuss in an issue first)
- Breaking API changes (require strong justification)
- Large refactoring (coordinate with maintainers)

## Communication

### Questions and Discussions

- **General Questions:** Open a GitHub Discussion
- **Bug Reports:** Open a GitHub Issue with reproduction steps
- **Feature Requests:** Open a GitHub Issue for discussion
- **Security Issues:** Use GitHub's private vulnerability reporting (see SECURITY.md)

### Getting Help

- Review existing documentation (README, AGENTS, API, etc.)
- Check closed issues for similar problems
- Ask in GitHub Discussions
- Be patient and respectful

## Code of Conduct

This project adheres to the Contributor Covenant Code of Conduct. By participating, you are expected to uphold this code. Please report unacceptable behavior through GitHub Discussions or by contacting repository maintainers.

See [CODE_OF_CONDUCT.md](../policies/code-of-conduct.md) for details.

## License

By contributing to AGDD, you agree that your contributions will be licensed under the MIT License.

## Recognition

Contributors will be recognized in:
- Git commit history
- GitHub contributors page
- Release notes for significant contributions

Thank you for contributing to AGDD!
