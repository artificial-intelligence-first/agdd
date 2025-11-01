from __future__ import annotations

from pathlib import Path

from magsag.worktree.git import parse_porcelain_z


def test_parse_porcelain_z_parses_multiple_entries() -> None:
    """Ensure porcelain parser returns structured worktree entries."""
    payload = b"\0".join(
        [
            b"worktree /repo",
            b"HEAD abcd1234",
            b"branch refs/heads/main",
            b"",
            b"worktree /repo/.worktrees/wt-123",
            b"HEAD deadbeef",
            b"branch refs/heads/wt/run/task",
            b"locked reason-for-lock",
            b"prunable gone",
            b"gitdir /repo/.git/worktrees/wt-123",
            b"",
            b"worktree /repo/.worktrees/detached",
            b"HEAD cafe4321",
            b"detached",
            b"",
            b"",
        ]
    )

    infos = parse_porcelain_z(payload)

    assert len(infos) == 3

    root = infos[0]
    assert root.path == Path("/repo")
    assert root.branch_short == "main"
    assert not root.locked

    managed = infos[1]
    assert managed.path == Path("/repo/.worktrees/wt-123")
    assert managed.branch_short == "wt/run/task"
    assert managed.locked
    assert managed.lock_reason == "reason-for-lock"
    assert managed.prunable
    assert managed.prunable_reason == "gone"
    assert managed.git_dir == Path("/repo/.git/worktrees/wt-123")

    detached = infos[2]
    assert detached.is_detached
    assert detached.head == "cafe4321"
