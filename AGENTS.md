# AGENTS.md

## Dev Environment Tips
- Use Python 3.12 with the [`uv`](https://docs.astral.sh/uv/) package manager available on `PATH`.
- From the repository root run `uv sync --extra dev` to install or refresh all runtime and development dependencies.
- Exercise the walking skeleton early: `uv run python -m agdd.cli validate` followed by `uv run python -m agdd.cli run hello --text "AGDD"`.
- (Optional) To integrate Flow Runner:
  - Clone `https://github.com/artificial-intelligence-first/flow-runner.git` alongside this repo.
  - Inside Flow Runner run `uv sync` then `uv pip install -e packages/mcprouter -e packages/flowrunner`.
  - Export `FLOW_RUNNER_PYTHONPATH="$(pwd)/packages"` (or source `tools/flowrunner_env.sh`) before calling `flowctl` commands.
- Keep Flow Runner artifacts current by running `uv run python tools/verify_vendor.py` whenever vendored schemas or sample flows change.

## Testing Instructions
- Run the core validation loop before every commit:
  - `uv run python -m agdd.cli validate`
  - `uv run python -m agdd.cli run hello --text "AGDD"`
- Execute automated checks from the repository root:
  - `uv run -m pytest -q`
  - `uv run python tools/check_docs.py`
- When Flow Runner is installed, confirm the runner boundary with:
  - `uv run python -m agdd.cli flow available`
  - `uv run python -m agdd.cli flow summarize --output governance/flow_summary.json`
  - `uv run python -m agdd.cli flow gate governance/flow_summary.json --policy policies/flow_governance.yaml`
- Add or update pytest coverage for new contracts, policies, or skills under `tests/`.

## Build & Deployment
- Produce a wheel with `uv build` to ensure packaged assets under `agdd/assets/` are bundled correctly.
- Smoke-test the generated artifact in a disposable virtual environment whenever assets or entry points change.
- Flow Runner integrations should log runs to `.runs/` so governance summaries can be generated and archived.

## Linting & Code Quality
- Enforce documentation and policy constraints with `uv run python tools/check_docs.py`.
- Maintain stateless, reusable skills under `agdd/skills/` and keep runner adapters in `agdd/runners/` focused on boundary logic.
- Update JSON Schemas in `contracts/` in tandem with registry changes, and keep governance thresholds in `policies/flow_governance.yaml` aligned with operational requirements.

## PR Instructions
- Capture planned work in `PLANS.md` before coding and record completed changes in `CHANGELOG.md` under `[Unreleased]`.
- Update terminology or policy definitions in `SSOT.md`; reference the SSOT from other docs rather than duplicating definitions.
- A pull request must demonstrate passing:
  - `uv run python -m agdd.cli validate`
  - `uv run python -m agdd.cli run hello --text "AGDD"`
  - `uv run -m pytest -q`
  - `uv run python tools/check_docs.py`
- Document any Flow Runner command expectations in the PR description when modifying runner-related code or policies.

## Security & Credentials
- Do not commit secrets or credentials; configuration should rely on environment variables and local setup scripts.
- When interacting with external services, prefer configurable endpoints and document any required secrets in secure channels outside the repository.
- Validate dependency integrity through `uv` and keep vendored files under version control so hash verification remains reproducible.
