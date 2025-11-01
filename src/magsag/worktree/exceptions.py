"""Custom exceptions for worktree operations."""

from __future__ import annotations

from dataclasses import dataclass
from subprocess import CompletedProcess
from typing import Sequence


class WorktreeError(RuntimeError):
    """Base exception for worktree related failures."""


class WorktreeNotFoundError(WorktreeError):
    """Raised when a requested worktree cannot be located."""


class WorktreeConflictError(WorktreeError):
    """Raised when attempting to create a conflicting worktree or branch."""


class WorktreeDirtyError(WorktreeError):
    """Raised when attempting to remove a worktree that is not clean."""


class WorktreeForbiddenError(WorktreeError):
    """Raised when a forbidden operation (policy violation) is attempted."""


class WorktreeLimitError(WorktreeForbiddenError):
    """Raised when concurrency or capacity limits are exceeded."""


@dataclass(slots=True)
class GitCommandError(WorktreeError):
    """Raised when an underlying Git command fails."""

    argv: Sequence[str]
    result: CompletedProcess[bytes]

    def __str__(self) -> str:
        stderr = (self.result.stderr or b"").decode("utf-8", errors="replace").strip()
        stdout = (self.result.stdout or b"").decode("utf-8", errors="replace").strip()
        details = stderr or stdout
        suffix = f": {details}" if details else ""
        return f"git command failed ({' '.join(self.argv)}){suffix}"
