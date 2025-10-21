# AGENTS.md

Operational guidance for the AG-Driven Development (AGDD) repository. The
instructions below supersede general documentation when you are running or
modifying code.

## Dev Environment Tips
- Use Python 3.12 with the [`uv`](https://docs.astral.sh/uv/) package manager.
  Install or refresh dependencies with `uv sync`, and include development tools
  when needed via `uv sync --extra dev`.
- Exercise the walking skeleton early: `uv run python -m agdd.cli validate`
  and `uv run python -m agdd.cli run hello --text "AGDD"` ensure the registry,
  contracts, and skills integrate correctly.
- Flow Runner integration is optional but recommended when working on runner
  boundaries:
  1. Clone https://github.com/artificial-intelligence-first/flow-runner.git
  2. From the Flow Runner repo, run `uv sync` followed by
     `uv pip install -e packages/mcprouter -e packages/flowrunner`
  3. Source `tools/flowrunner_env.sh` or export
     `FLOW_RUNNER_PYTHONPATH` so `flowctl` can import the runner modules
- Verify vendored Flow Runner assets with
  `uv run python tools/verify_vendor.py` whenever files under
  `agdd/assets/` or `examples/flowrunner/` change.
- Keep new skills stateless under `agdd/skills/`, register agents via
  `registry/agents/*.yaml`, and back descriptors with JSON Schemas under
  `contracts/`. Prefer Typer-based CLIs that invoke agents to maintain the
  AI-first workflow.

## Testing Instructions
- Run the required checks locally before committing:
  - `uv run -m pytest -q`
  - `uv run python tools/check_docs.py`
- Re-run the walking skeleton commands (`agdd.cli validate` and
  `agdd.cli run hello`) after changes that affect registry wiring, contracts,
  or skills.
- When Flow Runner is installed, validate the boundary with:
  - `uv run python -m agdd.cli flow available`
  - `uv run python -m agdd.cli flow summarize [--output <path>]`
  - `uv run python -m agdd.cli flow gate <summary.json> --policy policies/flow_governance.yaml`
- Add or update pytest coverage for any new contracts, policies, or skills.
  Tests live under `tests/` and must pass before a pull request is opened.

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

## Security & Credentials
- Do not commit secrets, API keys, or Flow Runner credentials. Use environment
  variables sourced via `tools/flowrunner_env.sh` for local experimentation.
- Keep governance thresholds in `policies/flow_governance.yaml` aligned with
  operational requirements. Update associated tests and documentation when
  thresholds or policy structures change.
- Review third-party dependencies during updates and run
  `uv run python tools/verify_vendor.py` after refreshing vendored artifacts to
  detect tampering.
