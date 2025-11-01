"""Typed structures representing Git worktree state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


@dataclass(slots=True)
class WorktreeInfo:
    """Machine-friendly representation of `git worktree list --porcelain -z` output."""

    path: Path
    head: str | None = None
    branch: str | None = None
    git_dir: Path | None = None
    is_bare: bool = False
    is_detached: bool = False
    locked: bool = False
    lock_reason: str | None = None
    prunable: bool = False
    prunable_reason: str | None = None
    extras: Mapping[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """Return the directory name of the worktree."""
        return self.path.name

    @property
    def branch_short(self) -> str | None:
        """Return branch name without refs/heads prefix when available."""
        if self.branch is None:
            return None
        if self.branch.startswith("refs/heads/"):
            return self.branch[len("refs/heads/") :]
        return self.branch

    @property
    def is_ephemeral(self) -> bool:
        """Check whether the branch follows the wt/<runId>/<task> convention."""
        short = self.branch_short
        return bool(short and short.startswith("wt/"))

    @property
    def run_id(self) -> str | None:
        """Extract run identifier from branch naming convention."""
        short = self.branch_short
        if not short:
            return None
        parts = short.split("/", 2)
        if len(parts) < 2 or parts[0] != "wt":
            return None
        return parts[1]

    @property
    def task_slug(self) -> str | None:
        """Extract task slug from branch naming convention."""
        short = self.branch_short
        if not short:
            return None
        parts = short.split("/", 2)
        if len(parts) < 3 or parts[0] != "wt":
            return None
        return parts[2]
