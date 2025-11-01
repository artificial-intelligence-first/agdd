---
title: Tracking Issue – mypy/ruff debt cleanup
status: closed
resolved: 2025-02-15
owner: platform-foundations
created: 2025-02-14
related_plans:
  - ../roadmap.md
  - ../../PLANS.md
---

# Summary
- `uv run mypy --strict src tests` and `uv run ruff check src tests` now pass without errors following debt cleanup.
- Runtime suites (`pytest`, `pytest -m slow`) continue to succeed, completing the “Full validation matrix green” exit criterion.

# Scope
- Audit and resolve all outstanding mypy strict errors across `src/` and `tests/`.
- Fix or silence (with justification) all `ruff check` findings in the same paths.
- Ensure CI runs for `mypy --strict` and `ruff` complete without failures.

# Acceptance
1. `uv run mypy --strict src tests` exits with status 0.
2. `uv run ruff check src tests` exits with status 0.
3. Any temporary ignores or `py.typed` adjustments are documented and linked from this issue.
4. `PLANS.md` “Full validation matrix green” remains checked once the above is satisfied.

# Resolution Notes
- `uv run mypy --strict src tests` exited 0 (2025-02-15).
- `uv run ruff check src tests` exited 0 (2025-02-15).
- Removed stale ignores/imports, tightened test annotations, and hardened provider adapters to satisfy strict typing.
- Updated `PLANS.md` to reflect static analysis completion.
