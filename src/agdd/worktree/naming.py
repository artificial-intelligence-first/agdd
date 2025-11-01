"""Naming helpers for worktree directories and branches."""

from __future__ import annotations

import re

_SAFE_SEGMENT = re.compile(r"[^a-z0-9._]+")


def sanitize_segment(segment: str, *, lower: bool = True) -> str:
    """
    Sanitize free-form identifiers for use in paths and branch names.

    Replaces unsafe characters with hyphens, collapses repeats, and enforces
    lowercase output by default.
    """
    cleaned = segment.strip()
    if lower:
        cleaned = cleaned.lower()
    cleaned = cleaned.replace(" ", "-")
    cleaned = _SAFE_SEGMENT.sub("-", cleaned)
    cleaned = cleaned.strip("-._")
    return cleaned or "x"


def branch_name(run_id: str, task: str) -> str:
    """Return the canonical ephemeral branch name."""
    return f"wt/{sanitize_segment(run_id)}/{sanitize_segment(task)}"


def directory_name(run_id: str, task: str, short_sha: str) -> str:
    """Return the canonical worktree directory name."""
    return f"wt-{sanitize_segment(run_id)}-{sanitize_segment(task)}-{short_sha}"
