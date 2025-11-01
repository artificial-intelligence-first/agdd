"""Tests for SQLite storage backend."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio

from magsag.storage.backends.sqlite import SQLiteStorageBackend
from magsag.storage.models import ApprovalTicketRecord, RunSnapshotRecord

pytestmark = pytest.mark.slow


@pytest_asyncio.fixture
async def storage() -> AsyncIterator[SQLiteStorageBackend]:
    """Create a temporary SQLite storage backend for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        backend = SQLiteStorageBackend(db_path=db_path, enable_fts=True)
        await backend.initialize()
        yield backend
        await backend.close()


@pytest.mark.asyncio
async def test_create_and_get_run(storage: SQLiteStorageBackend) -> None:
    """Test creating and retrieving a run."""
    run_id = "test-run-001"
    agent_slug = "test-agent"

    # Create run
    await storage.create_run(
        run_id=run_id,
        agent_slug=agent_slug,
        status="running",
    )

    # Retrieve run
    run = await storage.get_run(run_id)
    assert run is not None
    assert run["run_id"] == run_id
    assert run["agent_slug"] == agent_slug
    assert run["status"] == "running"


@pytest.mark.asyncio
async def test_append_and_get_events(storage: SQLiteStorageBackend) -> None:
    """Test appending and retrieving events."""
    run_id = "test-run-002"
    agent_slug = "test-agent"

    # Create run
    await storage.create_run(run_id=run_id, agent_slug=agent_slug)

    # Append events
    await storage.append_event(
        run_id=run_id,
        agent_slug=agent_slug,
        event_type="log",
        timestamp=datetime.now(timezone.utc),
        level="info",
        message="Test event 1",
        payload={"key": "value1"},
    )

    await storage.append_event(
        run_id=run_id,
        agent_slug=agent_slug,
        event_type="log",
        timestamp=datetime.now(timezone.utc),
        level="error",
        message="Test event 2",
        payload={"key": "value2"},
    )

    # Retrieve events
    events = []
    async for event in storage.get_events(run_id):
        events.append(event)

    assert len(events) == 2
    assert events[0]["msg"] == "Test event 1"
    assert events[1]["msg"] == "Test event 2"
    assert events[0]["level"] == "info"
    assert events[1]["level"] == "error"


@pytest.mark.asyncio
async def test_list_runs(storage: SQLiteStorageBackend) -> None:
    """Test listing runs with filters."""
    # Create multiple runs
    for i in range(5):
        await storage.create_run(
            run_id=f"run-{i:03d}",
            agent_slug="agent-a" if i % 2 == 0 else "agent-b",
            status="succeeded" if i < 3 else "failed",
        )

    # List all runs
    all_runs = await storage.list_runs(limit=10)
    assert len(all_runs) == 5

    # Filter by agent
    agent_a_runs = await storage.list_runs(agent_slug="agent-a", limit=10)
    assert len(agent_a_runs) == 3

    # Filter by status
    failed_runs = await storage.list_runs(status="failed", limit=10)
    assert len(failed_runs) == 2


@pytest.mark.asyncio
async def test_search_text(storage: SQLiteStorageBackend) -> None:
    """Test full-text search."""
    run_id = "test-run-003"
    agent_slug = "test-agent"

    # Create run
    await storage.create_run(run_id=run_id, agent_slug=agent_slug)

    # Append events with searchable content
    await storage.append_event(
        run_id=run_id,
        agent_slug=agent_slug,
        event_type="log",
        timestamp=datetime.now(timezone.utc),
        message="This is a test message about errors",
    )

    await storage.append_event(
        run_id=run_id,
        agent_slug=agent_slug,
        event_type="log",
        timestamp=datetime.now(timezone.utc),
        message="Another message about successful completion",
    )

    # Skip if FTS5 not available
    if not storage.enable_fts:
        pytest.skip("FTS5 not available in this SQLite build")

    # Search for "errors"
    results = await storage.search_text("errors", limit=10)
    assert len(results) == 1
    assert "errors" in results[0]["msg"]

    # Search for "successful"
    results = await storage.search_text("successful", limit=10)
    assert len(results) == 1
    assert "successful" in results[0]["msg"]


@pytest.mark.asyncio
async def test_update_run(storage: SQLiteStorageBackend) -> None:
    """Test updating run metadata."""
    run_id = "test-run-004"
    agent_slug = "test-agent"

    # Create run
    await storage.create_run(run_id=run_id, agent_slug=agent_slug, status="running")

    # Update run
    metrics = {"duration_ms": 1500, "token_count": 1000}
    await storage.update_run(
        run_id=run_id,
        status="succeeded",
        ended_at=datetime.now(timezone.utc),
        metrics=metrics,
    )

    # Verify update
    run = await storage.get_run(run_id)
    assert run is not None
    assert run["status"] == "succeeded"
    assert run["ended_at"] is not None
    assert run["metrics"]["duration_ms"] == 1500


@pytest.mark.asyncio
async def test_vacuum(storage: SQLiteStorageBackend) -> None:
    """Test vacuum functionality."""
    # Create some runs
    for i in range(3):
        await storage.create_run(
            run_id=f"run-{i:03d}",
            agent_slug="test-agent",
            status="succeeded",
        )

    # Dry run vacuum
    result = await storage.vacuum(hot_days=0, dry_run=True)
    assert result["dry_run"] is True
    assert result["runs_to_delete"] >= 0

    # Actual vacuum
    result = await storage.vacuum(hot_days=0, dry_run=False)


@pytest.mark.asyncio
async def test_approval_ticket_persistence(storage: SQLiteStorageBackend) -> None:
    """Test persisting approval tickets."""
    now = datetime.now(timezone.utc)
    await storage.create_run(
        run_id="run-approval-1",
        agent_slug="agent-approval",
        status="running",
    )
    record = ApprovalTicketRecord(
        ticket_id="ticket-123",
        run_id="run-approval-1",
        agent_slug="agent-approval",
        tool_name="tool.approval",
        masked_args={"param": "value"},
        args_hash="a" * 64,
        requested_at=now,
        expires_at=now + timedelta(minutes=5),
        status="pending",
        metadata={"scope": "unit-test"},
    )

    await storage.create_approval_ticket(record)

    fetched = await storage.get_approval_ticket("ticket-123")
    assert fetched is not None
    assert fetched.ticket_id == "ticket-123"
    assert fetched.status == "pending"

    record.status = "approved"
    record.resolved_at = now + timedelta(minutes=1)
    record.resolved_by = "approver@example.com"
    record.decision_reason = "Allowed"
    record.response = {"note": "Approved"}

    await storage.update_approval_ticket(record)

    updated = await storage.get_approval_ticket("ticket-123")
    assert updated is not None
    assert updated.status == "approved"
    assert updated.resolved_by == "approver@example.com"
    assert updated.decision_reason == "Allowed"

    pending = await storage.list_approval_tickets(run_id="run-approval-1")
    assert len(pending) == 1
    assert pending[0].ticket_id == "ticket-123"


@pytest.mark.asyncio
async def test_snapshot_persistence(storage: SQLiteStorageBackend) -> None:
    """Test persisting run snapshots via storage backend."""
    now = datetime.now(timezone.utc)
    await storage.create_run(
        run_id="run-durable-1",
        agent_slug="agent-durable",
        status="running",
    )

    record = RunSnapshotRecord(
        snapshot_id="snap-001",
        run_id="run-durable-1",
        step_id="step-1",
        state={"counter": 1},
        metadata={"agent_slug": "agent-durable"},
        created_at=now,
    )

    await storage.upsert_run_snapshot(record)

    latest = await storage.get_latest_run_snapshot("run-durable-1")
    assert latest is not None
    assert latest.step_id == "step-1"

    record.state = {"counter": 2}
    await storage.upsert_run_snapshot(record)

    snapshot = await storage.get_run_snapshot("run-durable-1", "step-1")
    assert snapshot is not None
    assert snapshot.state["counter"] == 2

    snapshots = await storage.list_run_snapshots("run-durable-1")
    assert len(snapshots) == 1
    assert snapshots[0].step_id == "step-1"

    deleted = await storage.delete_run_snapshots("run-durable-1")
    assert deleted >= 1


@pytest.mark.asyncio
async def test_vacuum_month_boundary(storage: SQLiteStorageBackend) -> None:
    """Test vacuum with hot_days that crosses month boundary."""
    # Create a test run
    await storage.create_run(
        run_id="test-run-month",
        agent_slug="test-agent",
        status="succeeded",
    )

    # Test with hot_days=30 (should handle month boundaries correctly)
    result = await storage.vacuum(hot_days=30, dry_run=True)
    assert result["dry_run"] is True
    assert "cutoff" in result
    # Should not raise ValueError even if current day < hot_days

    # Test with hot_days=7 on early days of month
    result = await storage.vacuum(hot_days=7, dry_run=True)
    assert result["dry_run"] is True
    assert "cutoff" in result
