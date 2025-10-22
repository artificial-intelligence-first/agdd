# AGENTS.md

Operational guidance for the AG-Driven Development (AGDD) repository. The
instructions below supersede general documentation when you are running or
modifying code.

## Subsystem-Specific Guides

For detailed guidance on specific subsystems, see:

- **[agents/AGENTS.md](agents/AGENTS.md)** - Agent development (MAG/SAG creation, testing, contracts)
- **[skills/AGENTS.md](skills/AGENTS.md)** - Skill development (stateless functions, composition, testing)

These subsystem guides provide specialized instructions that complement the project-wide procedures below.

## Dev Environment Tips
- Use Python 3.12 with the [`uv`](https://docs.astral.sh/uv/) package manager.
  Install or refresh dependencies with `uv sync`, and include development tools
  when needed via `uv sync --extra dev`.
- Test the agent orchestration system early:
  `echo '{"role":"Engineer","level":"Mid"}' | uv run agdd agent run offer-orchestrator-mag`
  ensures the registry, agent runner, contracts, and skills integrate correctly.
- Flow Runner integration is optional but recommended when working on runner
  boundaries. Use the automated setup script:
  ```bash
  make setup-flowrunner
  source scripts/flowrunner-env.sh
  ```
  Or manually:
  1. Run `./scripts/setup-flowrunner.sh`
  2. Source `scripts/flowrunner-env.sh` to configure environment variables
- Verify vendored Flow Runner assets with
  `uv run python tools/verify_vendor.py` whenever files under
  `agdd/assets/` or `examples/flowrunner/` change.
- Keep new skills stateless under `skills/` (see [skills/AGENTS.md](skills/AGENTS.md)),
  register agents in `agents/{main,sub}/<agent-slug>/agent.yaml` (see [agents/AGENTS.md](agents/AGENTS.md)),
  and define contracts with JSON Schemas under `contracts/`. Prefer Typer-based CLIs that
  invoke agents to maintain the AI-first workflow.
- **Creating New Agents:** Use the templates in `agents/_template/`:
  - `mag-template/` - Template for Main Agents (orchestrators)
  - `sag-template/` - Template for Sub-Agents (specialists)
  - Copy template, customize agent.yaml and code, then add tests
  - See [agents/AGENTS.md](agents/AGENTS.md) for detailed instructions
- **Creating New Skills:** Use the template in `skills/_template/`
  - See [skills/AGENTS.md](skills/AGENTS.md) for detailed instructions

## Testing Instructions

### Test Layers

AGDD uses a three-layer testing strategy:

#### 1. Unit Tests (`tests/unit/`)
Test individual components in isolation:
- **Registry:** Agent/skill resolution, entrypoint loading
- **Runner:** ObservabilityLogger, SkillRuntime, delegation logic
- **Contracts:** JSON Schema validation

Example:
```bash
uv run -m pytest tests/unit/ -v
```

#### 2. Agent Tests (`tests/agents/`)
Test MAG/SAG behavior with contract validation:
- **Input/Output Contracts:** Validate against JSON schemas
- **Fallback Logic:** Test error handling and partial failures
- **Observability:** Verify logs, metrics, and summaries are generated

Example:
```bash
uv run -m pytest tests/agents/ -v
```

#### 3. Integration Tests (`tests/integration/`)
Test end-to-end workflows via CLI:
- **E2E Flow:** Full MAG→SAG orchestration
- **Observability Artifacts:** Check `.runs/agents/<RUN_ID>/` contents
- **CLI Interface:** Test `agdd agent run` command

Example:
```bash
uv run -m pytest tests/integration/ -v
```

### Running Tests

- **All tests:**
  ```bash
  uv run -m pytest -q
  ```

- **With coverage:**
  ```bash
  uv run -m pytest --cov=agdd --cov-report=term-missing
  ```

- **Documentation checks:**
  ```bash
  uv run python tools/check_docs.py
  ```

### Manual Validation

- Test agent orchestration after changes:
  ```bash
  echo '{"role":"Engineer","level":"Mid"}' | uv run agdd agent run offer-orchestrator-mag
  ```

- Check observability artifacts:
  ```bash
  ls -la .runs/agents/<RUN_ID>/
  cat .runs/agents/<RUN_ID>/logs.jsonl
  ```

- When Flow Runner is installed:
  ```bash
  uv run agdd flow available
  uv run agdd flow summarize [--output <path>]
  uv run agdd flow gate <summary.json> --policy policies/flow_governance.yaml
  ```

### Adding Tests

When adding new features, ensure coverage at all three layers:
1. **Unit:** Test the component in isolation
2. **Agent:** Test contract compliance and error handling
3. **Integration:** Test the full workflow via CLI

All tests must pass before a pull request is opened.

## Build & Deployment
- Build distributable artifacts with `uv build`. Run this whenever bundled
  resources in `agdd/assets/` or packaging configuration changes to confirm the
  wheel contains the required data files.
- Spot-check the wheel by installing it into a disposable environment (e.g.,
  `uv venv --seed .venv-build && uv pip install dist/agdd-*.whl`) when packaging
  logic or bundled assets change materially.

## Linting & Code Quality
- Run `uv run ruff check .` to enforce formatting and linting rules (configured
  in `pyproject.toml`). Use `uv run ruff check . --fix` for safe autofixes.
- Enforce typing guarantees with `uv run mypy agdd tests tools`.
- Maintain observability instrumentation under `observability/` so generated
  summaries expose `runs`, `success_rate`, latency metrics, and MCP statistics.

## PR Instructions
- Update `PLANS.md` before starting significant work and record completed items
  in `CHANGELOG.md` under the `[Unreleased]` section.
- Centralize terminology or policy updates in `SSOT.md` and reference that file
  from other documentation instead of duplicating definitions.
- A pull request must document the Flow Runner or governance impact for changes
  touching runners, policies, or observability. Capture expected
  `agdd.cli flow ...` behaviors in the description when applicable.
- Only open a PR after all required commands succeed locally:
  `uv run -m pytest -q`, `uv run python tools/check_docs.py`, and the walking
  skeleton CLI checks listed above.

## MAG/SAG Development Guide

For detailed agent development procedures, see **[agents/AGENTS.md](agents/AGENTS.md)**.

**Quick Reference:**
- **MAG (Main Agent)**: Orchestrators with suffix `-mag` (e.g., `offer-orchestrator-mag`)
- **SAG (Sub-Agent)**: Specialists with suffix `-sag` (e.g., `compensation-advisor-sag`)
- **Templates**: Use `agents/_template/mag-template/` or `agents/_template/sag-template/`
- **Testing**: Three-layer strategy (unit, agent, integration)
- **Observability**: Artifacts in `.runs/agents/<RUN_ID>/`

See [agents/AGENTS.md](agents/AGENTS.md) for complete development workflow, contract creation, registry integration, and troubleshooting.

## Security & Credentials
- Do not commit secrets, API keys, or Flow Runner credentials. Use environment
  variables sourced via `scripts/flowrunner-env.sh` (generated by `make setup-flowrunner`).
- Keep governance thresholds in `policies/flow_governance.yaml` aligned with
  operational requirements. Update associated tests and documentation when
  thresholds or policy structures change.
- Review third-party dependencies during updates and run
  `uv run python tools/verify_vendor.py` after refreshing vendored artifacts to
  detect tampering.
