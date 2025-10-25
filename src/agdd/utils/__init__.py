"""Utility functions for AGDD framework."""

from __future__ import annotations

from pathlib import Path


def find_project_root(start_path: Path | None = None) -> Path:
    """
    Find the project root by looking for common project markers.

    Searches upward from the start path for common project root indicators
    like pyproject.toml, .git directory, or setup.py.

    Args:
        start_path: Starting path to search from. Defaults to current file location.

    Returns:
        Path to project root directory.

    Raises:
        RuntimeError: If project root cannot be found.
    """
    if start_path is None:
        start_path = Path(__file__).resolve()

    current = start_path.resolve()
    if current.is_file():
        current = current.parent

    markers = ["pyproject.toml", ".git", "setup.py", "setup.cfg"]

    while current != current.parent:
        for marker in markers:
            if (current / marker).exists():
                return current
        current = current.parent

    raise RuntimeError(f"Could not find project root from {start_path}")