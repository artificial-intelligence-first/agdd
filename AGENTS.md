# AGENTS (Local Playbook for AG-Driven Development (AGDD))

## Workflow
1. Ensure Python 3.12 + `uv` are available.
2. Install or refresh dependencies: `uv sync`.
3. Validate the AI-first walking skeleton: `uv run python -m agdd.cli validate` and `uv run python -m agdd.cli run hello --text 'AGDD'`.
4. (Optional) Install Flow Runner (see README) and verify the runner boundary: `uv run python -m agdd.cli flow available`.
5. When Flow Runner is installed in editable mode, set `FLOW_RUNNER_PYTHONPATH` so `flowctl` can import its modules.
6. Inspect Flow Runner artifacts with `uv run python -m agdd.cli flow summarize` when `.runs/` logs exist and persist the JSON via `--output`.
7. Enforce governance thresholds locally with `uv run python -m agdd.cli flow gate <summary.json>`.
8. Verify vendored assets via `uv run python tools/verify_vendor.py`.
9. Run automated checks: `uv run -m pytest -q` and `uv run python tools/check_docs.py`.
10. Smoke test packaging whenever bundled resources change: `uv build` followed by installing the wheel in a disposable virtual environment.

## Development Loop
- Extend or add skills under `agdd/skills/*`, keeping them reusable and stateless where possible.
- Register new agents in `registry/agents/*.yaml`, then update `registry/agents.yaml` / `registry/skills.yaml` if routing changes.
- Back new descriptors with JSON Schemas under `contracts/` and add pytest coverage for the contract.
- Prefer Typer-based CLIs that call into agents so manual workflows stay AI & AI Agent-first.
- Add or swap runner adapters under `agdd/runners/`; Flow Runner (`FlowRunner`) serves as the default implementation.
- Surface run telemetry via `observability/` tooling so CI and governance systems can consume consistent metrics (`runs`, `success_rate`, `avg_latency_ms`, `mcp`, `steps`).
- Keep `policies/flow_governance.yaml` in sync with operational requirements; update thresholds alongside changes to flows or infrastructure.
- Ensure CI jobs generate Flow Runner summaries (`flow summarize --output ...`) so Multi Agent Governance pipelines can enforce thresholds.

## PR Policy
- Update `PLANS.md` before coding and capture completion details in `CHANGELOG.md` (under `[Unreleased]`).
- Record terminology or policy updates in `SSOT.md` first; other docs should reference the SSOT rather than redefining terms.
- A pull request must demonstrate passing `uv run python tools/check_docs.py`, `uv run -m pytest -q`, and the walking-skeleton CLI commands above. Runner-related changes should document the expected `agdd.cli flow ...` behavior.
