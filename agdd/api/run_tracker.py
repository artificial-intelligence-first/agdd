"""Utilities for tracking and identifying agent runs from filesystem artifacts."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# Valid run_id pattern: alphanumeric + hyphens, reasonable length
# Prevents directory traversal attacks (../, absolute paths, etc.)
_RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,127}$")


def validate_run_id(run_id: str) -> None:
    """
    Validate run_id to prevent directory traversal attacks.

    Args:
        run_id: Run identifier to validate

    Raises:
        ValueError: If run_id contains invalid characters or patterns
    """
    if not _RUN_ID_PATTERN.match(run_id):
        raise ValueError(
            f"Invalid run_id: must be alphanumeric with hyphens, max 128 chars. Got: {run_id!r}"
        )

    # Additional safety: reject path separators and relative path components
    if "/" in run_id or "\\" in run_id or ".." in run_id:
        raise ValueError(f"Invalid run_id: contains path separators or relative components: {run_id!r}")


def _safe_run_path(base_dir: Path, run_id: str) -> Path:
    """
    Safely construct run directory path and verify it's within base_dir.

    Args:
        base_dir: Base directory containing agent runs
        run_id: Run identifier (will be validated)

    Returns:
        Path to run directory

    Raises:
        ValueError: If run_id is invalid or resolved path is outside base_dir
    """
    # Validate run_id format
    validate_run_id(run_id)

    # Construct path
    run_path = (base_dir / run_id).resolve()
    base_dir_resolved = base_dir.resolve()

    # Verify the resolved path is a direct child of base_dir
    # This prevents directory traversal even if validation is bypassed
    if run_path.parent != base_dir_resolved:
        raise ValueError(
            f"Security violation: run_id resolves outside base directory. "
            f"run_id={run_id!r}, base={base_dir_resolved}, resolved={run_path}"
        )

    return run_path


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
    Find newly created run_id by comparing snapshots.

    First tries to match by slug in summary.json, then falls back to
    finding the newest MAG directory created after started_at.

    Args:
        base_dir: Base directory containing agent runs
        before: Set of run directories before execution
        slug: Agent slug to match in summary.json (optional matching)
        started_at: Timestamp when execution started

    Returns:
        Run ID (directory name) if found, None otherwise
    """
    after = snapshot_runs(base_dir)
    new_dirs = after - before

    # First pass: Check new directories with mtime >= started_at and matching slug
    candidates = [d for d in new_dirs if d.stat().st_mtime >= started_at - 0.001]
    for d in sorted(candidates, key=lambda x: x.stat().st_mtime, reverse=True):
        summary = _read_json(d / "summary.json")
        if summary and summary.get("slug") == slug:
            return d.name

    # Second pass: If slug not found in summary.json, return newest MAG directory
    # This handles cases where ObservabilityLogger doesn't write slug to summary
    mag_dirs = [d for d in candidates if d.name.startswith("mag-")]
    if mag_dirs:
        # Return the most recently created MAG directory
        newest_mag = max(mag_dirs, key=lambda x: x.stat().st_mtime)
        return newest_mag.name

    # Third pass: Check all directories with matching slug and recent mtime
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
    """
    Read summary.json for a given run_id.

    Args:
        base_dir: Base directory containing agent runs
        run_id: Run identifier (validated for security)

    Returns:
        Parsed summary.json contents or None if not found/invalid

    Raises:
        ValueError: If run_id is malformed or attempts directory traversal
    """
    run_path = _safe_run_path(base_dir, run_id)
    return _read_json(run_path / "summary.json")


def read_metrics(base_dir: Path, run_id: str) -> dict[str, Any] | None:
    """
    Read metrics.json for a given run_id.

    Args:
        base_dir: Base directory containing agent runs
        run_id: Run identifier (validated for security)

    Returns:
        Parsed metrics.json contents or None if not found/invalid

    Raises:
        ValueError: If run_id is malformed or attempts directory traversal
    """
    run_path = _safe_run_path(base_dir, run_id)
    return _read_json(run_path / "metrics.json")


def open_logs_file(base_dir: Path, run_id: str) -> Path:
    """
    Get path to logs.jsonl file.

    Args:
        base_dir: Base directory containing agent runs
        run_id: Run identifier (validated for security)

    Returns:
        Path to logs.jsonl file

    Raises:
        ValueError: If run_id is malformed or attempts directory traversal
        FileNotFoundError: If logs.jsonl does not exist
    """
    run_path = _safe_run_path(base_dir, run_id)
    log_path = run_path / "logs.jsonl"
    if not log_path.exists():
        raise FileNotFoundError(f"Logs not found: {log_path}")
    return log_path
