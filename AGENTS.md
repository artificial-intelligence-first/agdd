# AGENTS.md: AI-Agent-Friendly Development Guide

## Purpose

This document provides machine-focused operational knowledge for AI coding agents working on the AGDD (AG-Driven Development) framework. It complements human-facing documentation with clear, imperative instructions for development procedures.

## Dev Environment Setup

### Prerequisites
- Python 3.12+
- uv package manager: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Installation
```bash
# Clone repository
git clone https://github.com/artificial-intelligence-first/agdd.git
cd agdd

# Copy environment template
cp .env.example .env
# Edit .env with API credentials (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)

# Development installation (recommended)
uv sync --extra dev

# Full installation (all optional features)
uv sync --extra dev --extra cache --extra faiss --extra redis --extra postgres --extra google --extra observability --extra mcp-server
```

### Optional Features
- `dev`: Testing, linting, type checking (required for development)
- `cache`: Semantic caching with numpy for embeddings
- `faiss`: FAISS-based vector similarity search
- `mcp-server`: MCP server support for Claude Desktop
- `redis`: Distributed rate limiting and Redis cache
- `postgres`: PostgreSQL/TimescaleDB storage backend
- `google`: Google Gemini provider support
- `observability`: OpenTelemetry and Langfuse integration

### Verify Installation
```bash
uv run -m pytest -q
```

## Testing Instructions

### Run All Tests
```bash
# Quick test run
uv run -m pytest -q

# Verbose output
uv run -m pytest -v

# With coverage
uv run -m pytest --cov=src/agdd --cov-report=html
```

### Run Specific Test Categories
```bash
# Agent tests only
uv run -m pytest tests/agents/ -v

# Runner tests only
uv run -m pytest tests/runner/ -v

# MCP integration tests
uv run -m pytest tests/mcp/ -v

# Storage layer tests
uv run -m pytest tests/storage/ -v
```

### Test Locations
- `tests/agents/` - Agent orchestration tests (MAG/SAG)
- `tests/runner/` - Flow Runner integration tests
- `tests/providers/` - Multi-provider LLM tests
- `tests/mcp/` - MCP integration tests
- `tests/storage/` - Storage backend tests
- `tests/routing/` - Routing and caching tests

### Test Requirements
- All new features must include tests
- Maintain or improve coverage (current: comprehensive)
- Tests must pass before PR submission

## Build & Package

### Build Distribution
```bash
# Build wheel and sdist
uv build

# Verify wheel contents
unzip -l dist/agdd-*.whl | grep assets/
```

### Verify Bundled Assets
```bash
# Check schemas and policies are included
uv run python ops/tools/verify_vendor.py
```

### Install from Wheel
```bash
# Create temporary venv and install
python -m venv /tmp/test-agdd
source /tmp/test-agdd/bin/activate
pip install dist/agdd-*.whl
agdd --help
deactivate
```

## Linting & Code Quality

### Pre-commit Hooks (Recommended)
```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run on all files
pre-commit run --all-files
```

### Manual Checks
```bash
# Ruff linting
uv run ruff check src/ tests/ ops/

# Ruff formatting
uv run ruff format src/ tests/ ops/

# Type checking (strict mode)
uv run mypy src/agdd tests/ ops/tools/

# YAML validation
uv run python -c "import yaml; yaml.safe_load(open('catalog/registry/agents.yaml'))"
```

### Code Quality Standards
- **Type Safety**: Full mypy strict mode compliance required
- **Formatting**: Ruff for linting and formatting (follows PEP 8)
- **Imports**: Organized alphabetically, no unused imports
- **Docstrings**: Required for public functions and classes
- **No warnings**: Fix all linter warnings before commit

## Documentation Validation

### Check Documentation Integrity
```bash
# Verify all required docs exist
uv run python ops/tools/check_docs.py

# Validate documentation cross-references
grep -r "docs/" README.md | while read line; do
  file=$(echo "$line" | grep -oP 'docs/[^)]+')
  [ -f "$file" ] || echo "Missing: $file"
done
```

### Required Documentation Files
- `README.md` - Project overview and quick start
- `AGENTS.md` - This file (machine-focused procedures)
- `CHANGELOG.md` - Version history (Keep a Changelog format)
- `PLANS.md` - ExecPlans location and governance
- `SSOT.md` - Terminology and policies
- `docs/guides/agent-development.md` - Agent development playbook
- `docs/guides/api-usage.md` - HTTP API reference
- `docs/storage.md` - Storage layer documentation

## PR Instructions

### Before Creating PR

1. **Update Documentation First**
   - Review `SSOT.md` for terminology
   - Update `PLANS.md` with execution plan if complex work
   - Update relevant guides in `docs/`

2. **Run All Validation**
   ```bash
   # Tests
   uv run -m pytest -q

   # Linting
   uv run ruff check src/ tests/ ops/

   # Type checking
   uv run mypy src/agdd tests/ ops/tools/

   # Documentation
   uv run python ops/tools/check_docs.py
   ```

3. **Update CHANGELOG.md**
   - Add entry to `## [Unreleased]` section
   - Use appropriate category: Added/Changed/Removed/Fixed/Security
   - Write from end-user perspective
   - Reference issue/PR numbers

### PR Format

**Title**: `<type>: <short description>`

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

**Description Template**:
```markdown
## Summary
Brief description of changes

## Changes
- Bullet list of specific changes
- Include file paths for major modifications

## Testing
- How changes were tested
- Any new test coverage added

## Documentation
- Updated documentation files
- Links to relevant docs

## Related Issues
Closes #123
```

### Branch Naming
- Feature: `feature/<short-description>`
- Bug fix: `fix/<short-description>`
- Documentation: `docs/<short-description>`
- Claude sessions: `claude/<description>-<session-id>`

### Commit Messages
```bash
# Format: <type>(<scope>): <subject>
# Examples:
git commit -m "feat(agent): add semantic cache support"
git commit -m "fix(api): correct error response format"
git commit -m "docs(guides): update API usage examples"
```

### Review Checklist
- [ ] All tests pass locally
- [ ] No linting errors
- [ ] Type checking passes (mypy strict)
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] No sensitive data in commits
- [ ] Commit messages follow convention

## Security & Credentials

### Credential Management
- **Never commit credentials**: Use `.env` files (listed in `.gitignore`)
- **API Keys**: Store in `.env`, load via `python-dotenv`
- **Secrets Detection**: Pre-commit hook detects private keys
- **Example File**: Keep `.env.example` updated with required keys (no values)

### Required Environment Variables
```bash
# LLM Providers (at least one required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Optional: Google Gemini
GOOGLE_API_KEY=...

# Optional: API Server
AGDD_API_KEY=your-secret-key
AGDD_GITHUB_TOKEN=ghp_...
AGDD_GITHUB_WEBHOOK_SECRET=...

# Optional: Rate Limiting
REDIS_URL=redis://localhost:6379/0

# Optional: Observability
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
```

### Security Scanning
```bash
# Check for private keys (pre-commit hook)
pre-commit run detect-private-key --all-files

# Verify no secrets in git history
git log -p | grep -i "api_key\|secret\|password"
```

## Common Tasks

### Agent Development
```bash
# Copy MAG template
cp -r catalog/agents/_template/mag-template catalog/agents/main/my-agent-mag

# Copy SAG template
cp -r catalog/agents/_template/sag-template catalog/agents/sub/my-agent-sag

# Update agent.yaml with your agent's metadata
# Update PERSONA.md with your agent's behavior
# Implement code/orchestrator.py (MAG) or code/advisor.py (SAG)

# Test your agent
uv run agdd agent run my-agent-mag --json examples/test_input.json
```

### Storage Management
```bash
# Initialize storage
uv run agdd data init

# Query runs
uv run agdd data query --agent my-agent-mag --limit 10

# Full-text search
uv run agdd data search "error rate limit"

# Clean old data
uv run agdd data vacuum --hot-days 7 --dry-run
```

### API Development
```bash
# Start API server (development mode with hot-reload)
AGDD_API_DEBUG=1 uv run uvicorn agdd.api.server:app --reload

# Test endpoints
curl -H "Authorization: Bearer $AGDD_API_KEY" http://localhost:8000/api/v1/agents | jq
```

### MCP Server
```bash
# Start MCP server
uv run agdd mcp serve

# With agent filtering
uv run agdd mcp serve --filter-agents offer-orchestrator-mag
```

## Makefile Commands

Common tasks are automated via Makefile:

```bash
make help              # Show all available targets
make test              # Run all tests
make test-agents       # Run agent tests only
make agent-run         # Execute sample MAG
make docs-check        # Validate documentation
make setup-flowrunner  # One-time Flow Runner setup
make flow-run          # Execute sample flow
```

## Integration with Other Conventions

### SSOT.md
Reference `SSOT.md` for canonical terminology. When introducing new concepts:
1. Add definition to `SSOT.md` first
2. Use consistent terminology in code and docs
3. Update `SSOT.md` front-matter change_log

### CHANGELOG.md
Update `CHANGELOG.md` when work is complete:
1. Add entry to `## [Unreleased]` section
2. Use standard categories (Added/Changed/Fixed/Removed/Security)
3. Write user-facing descriptions (not code details)

### PLANS.md
For complex work spanning multiple sessions:
1. Create ExecPlan in `collab/execplans/`
2. Update Progress section with timestamps
3. Document decisions and surprises
4. Link from `PLANS.md`

## Troubleshooting

### Common Issues

**Import errors after installation**
```bash
# Rebuild and reinstall
uv build
pip install --force-reinstall dist/agdd-*.whl
```

**Flow Runner not found**
```bash
# Run setup script
./ops/scripts/setup-flowrunner.sh
# Verify
uv run agdd flow available
```

**Pre-commit hooks failing**
```bash
# Update hooks
pre-commit autoupdate
# Run manually
pre-commit run --all-files
```

**Type checking errors**
```bash
# Install type stubs
uv sync --extra dev
# Check specific file
uv run mypy src/agdd/specific_file.py
```

## AI Agent Notes

When working on this codebase as an AI agent:

1. **Always read SSOT.md first** to understand terminology and policies
2. **Check PLANS.md** for active ExecPlans before starting work
3. **Update CHANGELOG.md** for all user-facing changes
4. **Run validation** before committing (tests, linting, type checking)
5. **Follow naming conventions** strictly (see SSOT.md)
6. **Document decisions** in ExecPlans for complex work
7. **Test agent implementations** end-to-end before submitting PR
8. **Preserve existing patterns** unless explicitly refactoring
9. **Ask for clarification** when requirements are ambiguous
10. **Never commit credentials** or sensitive data

## Quick Reference

### File Locations
- Agents: `catalog/agents/main/` (MAG), `catalog/agents/sub/` (SAG)
- Skills: `catalog/skills/`
- Contracts: `catalog/contracts/`
- Policies: `catalog/policies/`
- Registry: `catalog/registry/agents.yaml`, `catalog/registry/skills.yaml`
- Source: `src/agdd/`
- Tests: `tests/`
- Docs: `docs/guides/`, `docs/reference/`, `docs/development/`

### Key Commands
```bash
# Development
uv sync --extra dev                    # Install dev dependencies
uv run -m pytest -q                    # Run tests
uv run ruff check src/                 # Lint code
uv run mypy src/agdd                   # Type check

# Agents
uv run agdd agent run <mag-slug>       # Execute MAG
uv run agdd agent run <mag-slug> --json file.json  # With input file

# Storage
uv run agdd data init                  # Initialize storage
uv run agdd data query --agent <slug>  # Query runs

# API
uv run uvicorn agdd.api.server:app --reload  # Start API server

# MCP
uv run agdd mcp serve                  # Start MCP server

# Build
uv build                               # Build wheel
```

---

**Last Updated**: 2025-10-29
**Maintained By**: AGDD Core Team
**Questions**: See docs/guides/agent-development.md or open an issue
