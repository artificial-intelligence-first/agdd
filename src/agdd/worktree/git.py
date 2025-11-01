"""Low-level Git helpers for worktree operations."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

from agdd.utils import find_project_root

from .exceptions import GitCommandError
from .types import WorktreeInfo


def run(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """
    Execute a Git command returning the completed process.

    Args:
        args: Sequence of arguments that follow the `git` executable.
        cwd: Directory to execute the command from (defaults to project root).
        env: Optional environment overrides.
        check: When True, raise :class:`GitCommandError` on non-zero exit.
        timeout: Optional timeout in seconds.

    Returns:
        CompletedProcess with stdout/stderr captured as bytes.
    """
    command = ["git", *args]
    repo_root = cwd or find_project_root()
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    result = subprocess.run(
        command,
        cwd=str(repo_root),
        env=merged_env,
        capture_output=True,
        check=False,
        timeout=timeout,
    )

    if check and result.returncode != 0:
        raise GitCommandError(command, result)

    return result


def parse_porcelain_z(payload: bytes) -> list[WorktreeInfo]:
    """
    Parse `git worktree list --porcelain -z` output into structured records.

    Git emits NUL-separated key/value pairs with optional flag-only lines.
    """
    if not payload:
        return []

    items: list[WorktreeInfo] = []
    data: dict[str, object] = {}
    extras: dict[str, str] = {}

    for raw in payload.split(b"\0"):
        if not raw:
            continue
        entry = raw.decode("utf-8", errors="replace")

        if entry.startswith("worktree "):
            if data:
                items.append(_to_info(data, extras))
                data = {}
                extras = {}
            data["path"] = Path(entry.split(" ", 1)[1])
            continue

        if entry.startswith("HEAD "):
            data["head"] = entry.split(" ", 1)[1]
            continue

        if entry.startswith("branch "):
            data["branch"] = entry.split(" ", 1)[1]
            continue

        if entry.startswith("gitdir "):
            extras["gitdir"] = entry.split(" ", 1)[1]
            continue

        if entry == "bare":
            data["is_bare"] = True
            continue

        if entry == "detached":
            data["is_detached"] = True
            continue

        if entry.startswith("locked"):
            data["locked"] = True
            if " " in entry:
                data["lock_reason"] = entry.split(" ", 1)[1]
            continue

        if entry.startswith("prunable"):
            data["prunable"] = True
            if " " in entry:
                data["prunable_reason"] = entry.split(" ", 1)[1]
            continue

        key, _, value = entry.partition(" ")
        extras[key] = value

    if data:
        items.append(_to_info(data, extras))

    return items


def _to_info(data: Mapping[str, object], extras: Mapping[str, str]) -> WorktreeInfo:
    """Convert parsed dictionaries into WorktreeInfo dataclasses."""
    if "path" not in data:  # pragma: no cover - defensive guard
        raise ValueError("Missing worktree path in porcelain output")

    gitdir = extras.get("gitdir")
    remaining_extras = {k: v for k, v in extras.items() if k != "gitdir"}

    return WorktreeInfo(
        path=Path(data["path"]),
        head=data.get("head"),  # type: ignore[arg-type]
        branch=data.get("branch"),  # type: ignore[arg-type]
        git_dir=Path(gitdir) if gitdir else None,
        is_bare=bool(data.get("is_bare", False)),
        is_detached=bool(data.get("is_detached", False)),
        locked=bool(data.get("locked", False)),
        lock_reason=data.get("lock_reason"),  # type: ignore[arg-type]
        prunable=bool(data.get("prunable", False)),
        prunable_reason=data.get("prunable_reason"),  # type: ignore[arg-type]
        extras=remaining_extras,
    )
