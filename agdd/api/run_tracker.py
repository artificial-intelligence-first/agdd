"""Utilities for tracking and identifying agent runs from filesystem artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def snapshot_runs(base_dir: Path) -> set[Path]:
    """
    Snapshot all run directories in base_dir.

    Args:
        base_dir: Base directory containing agent runs

    Returns:
        Set of Path objects representing run directories
    """
    if not base_dir.exists():
        return set()
    return {d for d in base_dir.iterdir() if d.is_dir()}


def _read_json(path: Path) -> dict[str, Any] | None:
    """Read JSON file, returning None on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_new_run_id(
    base_dir: Path,
    before: set[Path],
    slug: str,
    started_at: float,
) -> str | None:
    """
    Find newly created run_id by comparing snapshots and matching slug.

    Args:
        base_dir: Base directory containing agent runs
        before: Set of run directories before execution
        slug: Agent slug to match in summary.json
        started_at: Timestamp when execution started

    Returns:
        Run ID (directory name) if found, None otherwise
    """
    after = snapshot_runs(base_dir)
    new_dirs = after - before

    # First pass: Check new directories with mtime >= started_at
    candidates = [d for d in new_dirs if d.stat().st_mtime >= started_at - 0.001]
    for d in sorted(candidates, key=lambda x: x.stat().st_mtime, reverse=True):
        summary = _read_json(d / "summary.json")
        if summary and summary.get("slug") == slug:
            return d.name

    # Second pass: Check all directories (including before) with matching slug and recent mtime
    # This handles cases where directory already existed but was updated
    for d in sorted(after, key=lambda x: x.stat().st_mtime, reverse=True):
        summary = _read_json(d / "summary.json")
        if (
            summary
            and summary.get("slug") == slug
            and d.stat().st_mtime >= started_at - 2.0  # 2 second tolerance
        ):
            return d.name

    return None


def read_summary(base_dir: Path, run_id: str) -> dict[str, Any] | None:
    """Read summary.json for a given run_id."""
    return _read_json(base_dir / run_id / "summary.json")


def read_metrics(base_dir: Path, run_id: str) -> dict[str, Any] | None:
    """Read metrics.json for a given run_id."""
    return _read_json(base_dir / run_id / "metrics.json")


def open_logs_file(base_dir: Path, run_id: str) -> Path:
    """
    Get path to logs.jsonl file.

    Args:
        base_dir: Base directory containing agent runs
        run_id: Run identifier

    Returns:
        Path to logs.jsonl file

    Raises:
        FileNotFoundError: If logs.jsonl does not exist
    """
    log_path = base_dir / run_id / "logs.jsonl"
    if not log_path.exists():
        raise FileNotFoundError(f"Logs not found: {log_path}")
    return log_path
