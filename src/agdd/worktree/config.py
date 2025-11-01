"""Configuration helpers for worktree operations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from agdd.utils import find_project_root


def _get_env(name: str, default: str | None = None) -> str | None:
    """Fetch an environment variable returning the default when unset or empty."""
    value = os.environ.get(name)
    if value is None:
        return default
    trimmed = value.strip()
    return trimmed if trimmed else default


def _resolve_root(raw: str | None) -> Path:
    """Resolve the configured worktree root."""
    project_root = find_project_root()
    if raw:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = (project_root / candidate).resolve()
    else:
        candidate = (project_root.parent / ".worktrees").resolve()
    return candidate


@dataclass(frozen=True, slots=True)
class WorktreeSettings:
    """Resolved configuration for worktree management."""

    root: Path
    max_concurrency: int
    ttl_spec: str


@lru_cache
def get_worktree_settings() -> WorktreeSettings:
    """Return memoized worktree settings."""
    root = _resolve_root(_get_env("AGDD_WORKTREES_ROOT"))
    # Create the directory eagerly so downstream code can rely on existence.
    root.mkdir(parents=True, exist_ok=True)

    max_concurrency_raw = _get_env("AGDD_WT_MAX_CONCURRENCY", "8")
    try:
        max_concurrency = max(1, int(max_concurrency_raw))
    except ValueError as exc:
        raise ValueError(
            f"Invalid AGDD_WT_MAX_CONCURRENCY value: {max_concurrency_raw!r}"
        ) from exc

    ttl_spec = _get_env("AGDD_WT_TTL", "14d")

    return WorktreeSettings(root=root, max_concurrency=max_concurrency, ttl_spec=ttl_spec)


def ensure_within_root(path: Path, root: Path | None = None) -> Path:
    """
    Ensure the provided path resides within the configured worktree root.

    Args:
        path: Candidate path (absolute or relative).
        root: Optional explicit root; defaults to configured root.

    Returns:
        The resolved absolute path when it lies under the root.

    Raises:
        ValueError: If path escapes the root directory.
    """
    base = root or get_worktree_settings().root
    resolved = path if path.is_absolute() else base / path
    resolved = resolved.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Path {resolved} escapes worktree root {base}") from exc
    return resolved
