"""
Git worktree management utilities for MAGSAG.

This package provides a cohesive interface for creating, listing, and managing
Git worktrees that back concurrent AI task execution.
"""

from .config import WorktreeSettings, get_worktree_settings
from .events import WorktreeEvent, get_event_bus, publish_event
from .manager import WorktreeManager, WorktreeRecord, force_removal_allowed
from .types import WorktreeInfo
from .exceptions import (
    WorktreeError,
    WorktreeConflictError,
    WorktreeDirtyError,
    WorktreeForbiddenError,
    WorktreeLimitError,
    WorktreeNotFoundError,
    GitCommandError,
)

__all__ = [
    "WorktreeSettings",
    "WorktreeInfo",
    "WorktreeError",
    "WorktreeConflictError",
    "WorktreeDirtyError",
    "WorktreeForbiddenError",
    "WorktreeLimitError",
    "WorktreeNotFoundError",
    "GitCommandError",
    "WorktreeManager",
    "WorktreeRecord",
    "WorktreeEvent",
    "publish_event",
    "get_event_bus",
    "force_removal_allowed",
    "get_worktree_settings",
]
