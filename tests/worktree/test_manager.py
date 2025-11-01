from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from magsag.worktree import (
    WorktreeConflictError,
    WorktreeForbiddenError,
    WorktreeLimitError,
    WorktreeManager,
    WorktreeRecord,
    WorktreeSettings,
    get_event_bus,
)
from magsag.worktree.metadata import WorktreeMetadata, load_metadata
from magsag.worktree.naming import branch_name
from magsag.worktree.types import WorktreeInfo


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, stdout=subprocess.DEVNULL)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "config", "user.email", "magsag@example.com")
    _run_git(repo, "config", "user.name", "MAGSAG Tests")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "initial")
    _run_git(repo, "checkout", "-b", "base")
    return repo


@pytest.fixture
def manager(tmp_path: Path, git_repo: Path) -> WorktreeManager:
    root = tmp_path / "worktrees"
    root.mkdir(parents=True, exist_ok=True)
    settings = WorktreeSettings(root=root, max_concurrency=4, ttl_spec="7d")
    return WorktreeManager(settings=settings, repo_root=git_repo)


@pytest.mark.asyncio
async def test_worktree_lifecycle_emits_events_and_metadata(manager: WorktreeManager) -> None:
    bus = get_event_bus()
    queue = await bus.register()
    try:
        record = await asyncio.to_thread(
            manager.create,
            run_id="run-123",
            task="demo-task",
            base="base",
            auto_lock=True,
            lock_reason="initial-lock",
        )

        create_event = await asyncio.wait_for(queue.get(), timeout=5)
        assert create_event.name == "worktree.create"
        lock_event = await asyncio.wait_for(queue.get(), timeout=5)
        assert lock_event.name == "worktree.lock"
        assert lock_event.payload["lock_reason"] == "initial-lock"

        metadata = load_metadata(record.info.path)
        assert metadata is not None
        assert metadata.run_id == "run-123"
        assert metadata.task == "demo-task"
        assert metadata.branch == record.info.branch_short

        unlocked = await asyncio.to_thread(manager.unlock, "run-123")
        assert not unlocked.info.locked
        unlock_event = await asyncio.wait_for(queue.get(), timeout=5)
        assert unlock_event.name == "worktree.unlock"
        assert unlock_event.payload["locked"] is False

        relocked = await asyncio.to_thread(manager.lock, "run-123", reason="gate")
        assert relocked.info.locked
        relock_event = await asyncio.wait_for(queue.get(), timeout=5)
        assert relock_event.name == "worktree.lock"
        assert relock_event.payload["lock_reason"] == "gate"

        await asyncio.to_thread(manager.unlock, "run-123")
        post_unlock = await asyncio.wait_for(queue.get(), timeout=5)
        assert post_unlock.name == "worktree.unlock"
        assert post_unlock.payload["locked"] is False

        await asyncio.to_thread(manager.remove, "run-123")
        remove_event = await asyncio.wait_for(queue.get(), timeout=5)
        assert remove_event.name == "worktree.remove"
        assert remove_event.payload["force"] is False
        prune_event = await asyncio.wait_for(queue.get(), timeout=5)
        assert prune_event.name == "worktree.prune"
        assert prune_event.payload["after"] == 0

        await asyncio.to_thread(manager.repair)
        repair_event = await asyncio.wait_for(queue.get(), timeout=5)
        assert repair_event.name == "worktree.repair"
        assert repair_event.payload["status"] == "ok"

    finally:
        await bus.unregister(queue)


def test_create_allows_protected_base_when_branching(
    manager: WorktreeManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = manager.create(
        run_id="run-main",
        task="allowed",
        base="main",
    )
    try:
        assert record.info.branch_short is not None
        assert record.metadata is not None
        assert record.metadata.base == "main"
    finally:
        monkeypatch.setenv("MAGSAG_WT_ALLOW_FORCE", "1")
        manager.remove("run-main", force=True)


def test_detached_creation_blocked_on_protected_base(manager: WorktreeManager) -> None:
    with pytest.raises(WorktreeForbiddenError):
        manager.create(
            run_id="run-main-detach",
            task="forbidden",
            base="main",
            detach=True,
        )


def test_create_rejects_existing_branch(manager: WorktreeManager) -> None:
    branch = branch_name("run-existing", "demo-task")
    _run_git(manager.repo_root, "branch", branch, "base")

    with pytest.raises(WorktreeConflictError):
        manager.create(
            run_id="run-existing",
            task="demo-task",
            base="base",
        )


def test_concurrency_limit_enforced(
    manager: WorktreeManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    limited_settings = WorktreeSettings(
        root=manager.settings.root,
        max_concurrency=1,
        ttl_spec=manager.settings.ttl_spec,
    )
    limited_manager = WorktreeManager(settings=limited_settings, repo_root=manager.repo_root)

    occupied = manager.settings.root / "wt-run-occupied-demo"
    occupied.mkdir(parents=True, exist_ok=True)
    info = WorktreeInfo(
        path=occupied,
        branch="refs/heads/wt/run-occupied/demo",
    )
    metadata = WorktreeMetadata(
        run_id="run-occupied",
        task="demo",
        base="base",
        branch="wt/run-occupied/demo",
        short_sha="123abc",
    )
    existing_record = WorktreeRecord(info=info, metadata=metadata)
    monkeypatch.setattr(limited_manager, "managed_records", lambda: [existing_record])

    with pytest.raises(WorktreeLimitError):
        limited_manager.create(run_id="run-new", task="demo", base="base")


def test_force_removal_requires_ci_flag(
    manager: WorktreeManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    guarded = manager.settings.root / "wt-run-guard-task"
    guarded.mkdir(parents=True, exist_ok=True)
    info = WorktreeInfo(
        path=guarded,
        branch="refs/heads/wt/run-guard/task",
    )
    metadata = WorktreeMetadata(
        run_id="run-guard",
        task="task",
        base="base",
        branch="wt/run-guard/task",
        short_sha="abc123",
    )
    record = WorktreeRecord(info=info, metadata=metadata)
    monkeypatch.setattr(manager, "managed_records", lambda: [record])

    with pytest.raises(WorktreeForbiddenError):
        manager.remove("run-guard", force=True)


def test_create_supports_detach_and_no_checkout(
    manager: WorktreeManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = manager.create(
        run_id="run-detach",
        task="demo-detach",
        base="base",
        detach=True,
        no_checkout=True,
    )
    try:
        assert record.info.is_detached
        assert record.metadata is not None
        assert record.metadata.detach is True
        assert record.metadata.no_checkout is True
        assert record.info.branch_short is None
    finally:
        monkeypatch.setenv("MAGSAG_WT_ALLOW_FORCE", "1")
        manager.remove("run-detach", force=True)
