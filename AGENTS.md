# AGENTS (Local Playbook for AG-Driven Development (AGDD))
## Dev Setup
- Use Python 3.12 with `uv`. After `uv sync`, `uv run -m pytest -q` must pass.
## Run
- Documentation guardrails: `uv run python tools/check_docs.py`
- Tests: `uv run -m pytest -q`
## PR Policy
- Update PLANS.md (the ExecPlan) before making changes and append CHANGELOG.md when complete.
- Record terminology or policy updates in SSOT.md first; it remains the single source of truth.
