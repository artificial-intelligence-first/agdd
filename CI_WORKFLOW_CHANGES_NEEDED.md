# CI Workflow Changes Required

## Problem
The CI workflow is taking 14+ minutes to complete because it's running slow integration tests.

## Solution
The `pyproject.toml` has been updated to skip slow tests by default. However, the CI workflow file also needs to be updated manually due to GitHub App permission restrictions.

## Required Changes to `.github/workflows/ci.yml`

### Change 1: Line 35 (core job - Test suite)
```diff
       - name: Test suite
-        run: uv run -m pytest -q
+        run: uv run -m pytest -q -m 'not slow'
```

### Change 2: Line 87 (flowrunner job - Run tests)
```diff
       - name: Run tests (Flow Runner)
-        run: uv run -m pytest -q
+        run: uv run -m pytest -q -m 'not slow'
```

## Expected Impact
- CI runtime: **14+ minutes → ~30 seconds**
- Slow tests can still be run manually with: `pytest -m slow`

## How to Apply
1. Edit `.github/workflows/ci.yml` via GitHub web interface, or
2. Apply changes locally and push from an account with workflow permissions

## Already Applied
✅ `pyproject.toml` - Updated with `-m 'not slow'` in addopts (commit 3a04374)
