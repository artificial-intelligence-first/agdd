from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from magsag.worktree import WorktreeConflictError, WorktreeRecord
from magsag.worktree.metadata import WorktreeMetadata
from magsag.worktree.types import WorktreeInfo


@pytest.fixture
def client() -> Iterator[TestClient]:
    from magsag.api.server import app

    with TestClient(app) as test_client:
        yield test_client


def _make_record() -> WorktreeRecord:
    info = WorktreeInfo(
        path=Path("/tmp/.worktrees/wt-run-task-abc123"),
        head="abcdef1",
        branch="refs/heads/wt/run/task",
        locked=False,
    )
    meta = WorktreeMetadata(
        run_id="run-1",
        task="task-1",
        base="base-branch",
        short_sha="abc123",
        branch="wt/run/task",
        created_at=datetime.now(timezone.utc),
        detach=False,
        no_checkout=True,
    )
    return WorktreeRecord(info=info, metadata=meta)


def test_list_worktrees_returns_records(client: TestClient) -> None:
    record = _make_record()
    with patch("magsag.api.routes.worktrees.WorktreeManager") as manager_cls:
        manager = MagicMock()
        manager.managed_records.return_value = [record]
        manager_cls.return_value = manager

        response = client.get("/api/v1/worktrees")

        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["run_id"] == "run-1"
        assert payload[0]["branch"] == "wt/run/task"
        assert payload[0]["no_checkout"] is True


def test_create_worktree_propagates_conflicts(client: TestClient) -> None:
    with patch("magsag.api.routes.worktrees.WorktreeManager") as manager_cls:
        manager = MagicMock()
        manager.create.side_effect = WorktreeConflictError("exists")
        manager_cls.return_value = manager

        response = client.post(
            "/api/v1/worktrees",
            json={"run_id": "run-2", "task": "demo", "base": "base"},
        )

        assert response.status_code == 409
        payload = response.json()
        assert payload["code"] == "worktree_conflict"


def test_delete_worktree_invokes_manager(client: TestClient) -> None:
    with patch("magsag.api.routes.worktrees.WorktreeManager") as manager_cls:
        manager = MagicMock()
        manager_cls.return_value = manager

        response = client.delete("/api/v1/worktrees/run-1")

        assert response.status_code == 204
        manager.remove.assert_called_once_with("run-1", force=False)


def test_lock_and_unlock_worktree(client: TestClient) -> None:
    base_locked = _make_record()
    locked_record = WorktreeRecord(
        info=replace(base_locked.info, locked=True),
        metadata=base_locked.metadata,
    )
    base_unlocked = _make_record()
    unlocked_record = WorktreeRecord(
        info=replace(base_unlocked.info, locked=False),
        metadata=base_unlocked.metadata,
    )
    with patch("magsag.api.routes.worktrees.WorktreeManager") as manager_cls:
        manager = MagicMock()
        manager.lock.return_value = locked_record
        manager.unlock.return_value = unlocked_record
        manager_cls.return_value = manager

        lock_response = client.post(
            "/api/v1/worktrees/run-1/lock",
            json={"reason": "hold"},
        )
        assert lock_response.status_code == 200
        assert lock_response.json()["locked"] is True

        unlock_response = client.post("/api/v1/worktrees/run-1/unlock")
        assert unlock_response.status_code == 200
        manager.unlock.assert_called_once_with("run-1")
