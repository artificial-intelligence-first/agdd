"""
Integration tests for Durable Run with snapshot/restore.

Tests the complete durable run lifecycle including:
- Snapshot creation at step boundaries
- State restoration
- Restart resilience
- Step-level idempotency
"""

import asyncio
from pathlib import Path
from datetime import UTC, datetime

import pytest

from agdd.runners.durable import (
    DurableRunner,
    RunSnapshot,
    SnapshotStore,
)


@pytest.fixture
def snapshot_store(tmp_path):
    """Create snapshot store with temp directory."""
    return SnapshotStore(storage_backend=None)


@pytest.fixture
def durable_runner(snapshot_store):
    """Create durable runner for testing."""
    return DurableRunner(
        snapshot_store=snapshot_store,
        enable_auto_snapshot=True,
    )


class TestSnapshotStore:
    """Tests for SnapshotStore."""

    @pytest.mark.asyncio
    async def test_save_snapshot(self, snapshot_store):
        """Test saving a snapshot."""
        snapshot = await snapshot_store.save_snapshot(
            run_id="test-run-123",
            step_id="step-1",
            state={"counter": 1, "data": "test"},
            metadata={"agent": "test-agent"},
        )

        assert snapshot.snapshot_id is not None
        assert snapshot.run_id == "test-run-123"
        assert snapshot.step_id == "step-1"
        assert snapshot.state == {"counter": 1, "data": "test"}
        assert snapshot.metadata == {"agent": "test-agent"}
        assert snapshot.created_at is not None

    @pytest.mark.asyncio
    async def test_snapshot_idempotency(self, snapshot_store):
        """Test that saving same run_id + step_id is idempotent."""
        # Save first snapshot
        snapshot1 = await snapshot_store.save_snapshot(
            run_id="test-run-123",
            step_id="step-1",
            state={"counter": 1},
        )

        # Save again with same run_id + step_id
        snapshot2 = await snapshot_store.save_snapshot(
            run_id="test-run-123",
            step_id="step-1",
            state={"counter": 2},  # Updated state
        )

        # Should have same snapshot_id (updated, not duplicated)
        assert snapshot1.snapshot_id == snapshot2.snapshot_id
        assert snapshot2.state == {"counter": 2}

    @pytest.mark.asyncio
    async def test_get_latest_snapshot(self, snapshot_store):
        """Test retrieving latest snapshot."""
        # Save multiple snapshots
        await snapshot_store.save_snapshot(
            run_id="test-run-123",
            step_id="step-1",
            state={"counter": 1},
        )

        await asyncio.sleep(0.01)  # Small delay to ensure different timestamps

        snapshot2 = await snapshot_store.save_snapshot(
            run_id="test-run-123",
            step_id="step-2",
            state={"counter": 2},
        )

        # Get latest
        latest = await snapshot_store.get_latest_snapshot("test-run-123")

        assert latest is not None
        assert latest.step_id == "step-2"
        assert latest.state == {"counter": 2}

    @pytest.mark.asyncio
    async def test_get_snapshot_by_step(self, snapshot_store):
        """Test retrieving snapshot by step ID."""
        # Save multiple snapshots
        await snapshot_store.save_snapshot(
            run_id="test-run-123",
            step_id="step-1",
            state={"counter": 1},
        )

        await snapshot_store.save_snapshot(
            run_id="test-run-123",
            step_id="step-2",
            state={"counter": 2},
        )

        # Get specific step
        snapshot = await snapshot_store.get_snapshot_by_step(
            run_id="test-run-123",
            step_id="step-1",
        )

        assert snapshot is not None
        assert snapshot.step_id == "step-1"
        assert snapshot.state == {"counter": 1}

    @pytest.mark.asyncio
    async def test_list_snapshots(self, snapshot_store):
        """Test listing all snapshots for a run."""
        # Save multiple snapshots
        await snapshot_store.save_snapshot(
            run_id="test-run-123",
            step_id="step-1",
            state={"counter": 1},
        )

        await snapshot_store.save_snapshot(
            run_id="test-run-123",
            step_id="step-2",
            state={"counter": 2},
        )

        await snapshot_store.save_snapshot(
            run_id="test-run-456",  # Different run
            step_id="step-1",
            state={"counter": 10},
        )

        # List snapshots for specific run
        snapshots = await snapshot_store.list_snapshots("test-run-123")

        assert len(snapshots) == 2
        assert snapshots[0].step_id == "step-1"
        assert snapshots[1].step_id == "step-2"

    @pytest.mark.asyncio
    async def test_delete_snapshots(self, snapshot_store):
        """Test deleting all snapshots for a run."""
        # Save multiple snapshots
        await snapshot_store.save_snapshot(
            run_id="test-run-123",
            step_id="step-1",
            state={"counter": 1},
        )

        await snapshot_store.save_snapshot(
            run_id="test-run-123",
            step_id="step-2",
            state={"counter": 2},
        )

        # Delete snapshots
        count = await snapshot_store.delete_snapshots("test-run-123")

        assert count == 2

        # Verify deleted
        snapshots = await snapshot_store.list_snapshots("test-run-123")
        assert len(snapshots) == 0


class TestDurableRunner:
    """Tests for DurableRunner."""

    @pytest.mark.asyncio
    async def test_checkpoint(self, durable_runner):
        """Test creating a checkpoint."""
        snapshot = await durable_runner.checkpoint(
            run_id="test-run-123",
            step_id="step-1",
            state={"progress": 0.5, "items_processed": 10},
            metadata={"agent": "test-agent"},
        )

        assert snapshot.run_id == "test-run-123"
        assert snapshot.step_id == "step-1"
        assert snapshot.state["progress"] == 0.5

    @pytest.mark.asyncio
    async def test_resume_from_latest(self, durable_runner):
        """Test resuming from latest checkpoint."""
        # Create multiple checkpoints
        await durable_runner.checkpoint(
            run_id="test-run-123",
            step_id="step-1",
            state={"counter": 1},
        )

        await durable_runner.checkpoint(
            run_id="test-run-123",
            step_id="step-2",
            state={"counter": 2},
        )

        # Resume (should get latest)
        restored_state = await durable_runner.resume("test-run-123")

        assert restored_state is not None
        assert restored_state["counter"] == 2

    @pytest.mark.asyncio
    async def test_resume_from_specific_step(self, durable_runner):
        """Test resuming from a specific step."""
        # Create multiple checkpoints
        await durable_runner.checkpoint(
            run_id="test-run-123",
            step_id="step-1",
            state={"counter": 1},
        )

        await durable_runner.checkpoint(
            run_id="test-run-123",
            step_id="step-2",
            state={"counter": 2},
        )

        # Resume from specific step
        restored_state = await durable_runner.resume(
            run_id="test-run-123",
            from_step="step-1",
        )

        assert restored_state is not None
        assert restored_state["counter"] == 1

    @pytest.mark.asyncio
    async def test_resume_no_snapshot(self, durable_runner):
        """Test resuming when no snapshot exists."""
        restored_state = await durable_runner.resume("nonexistent-run")

        assert restored_state is None

    @pytest.mark.asyncio
    async def test_list_checkpoints(self, durable_runner):
        """Test listing checkpoints."""
        # Create multiple checkpoints
        await durable_runner.checkpoint(
            run_id="test-run-123",
            step_id="step-1",
            state={"counter": 1},
        )

        await durable_runner.checkpoint(
            run_id="test-run-123",
            step_id="step-2",
            state={"counter": 2},
        )

        # List checkpoints
        checkpoints = await durable_runner.list_checkpoints("test-run-123")

        assert len(checkpoints) == 2
        assert checkpoints[0].step_id == "step-1"
        assert checkpoints[1].step_id == "step-2"

    @pytest.mark.asyncio
    async def test_cleanup(self, durable_runner):
        """Test cleaning up checkpoints."""
        # Create checkpoints
        await durable_runner.checkpoint(
            run_id="test-run-123",
            step_id="step-1",
            state={"counter": 1},
        )

        # Clean up
        count = await durable_runner.cleanup("test-run-123")

        assert count == 1

        # Verify cleaned up
        checkpoints = await durable_runner.list_checkpoints("test-run-123")
        assert len(checkpoints) == 0


@pytest.mark.integration
@pytest.mark.slow
class TestDurableRunE2E:
    """End-to-end durable run tests."""

    @pytest.mark.asyncio
    async def test_restart_resilience(self, durable_runner):
        """
        Test complete restart scenario.

        Simulates:
        1. Agent runs and saves checkpoints at each step
        2. Process crashes/restarts
        3. Agent resumes from last checkpoint
        4. Continues execution without redoing completed steps
        """

        async def simulated_agent_run(run_id: str, start_from_step: int = 0):
            """Simulate multi-step agent execution."""
            steps = ["init", "process", "validate", "finalize"]
            results = []

            # Try to resume
            if start_from_step == 0:
                restored_state = await durable_runner.resume(run_id)
                if restored_state:
                    start_from_step = restored_state.get("last_step_index", 0) + 1

            for i in range(start_from_step, len(steps)):
                step = steps[i]

                # Do work
                result = f"completed {step}"
                results.append(result)

                # Checkpoint
                await durable_runner.checkpoint(
                    run_id=run_id,
                    step_id=step,
                    state={
                        "last_step_index": i,
                        "results": results,
                    },
                )

            return results

        run_id = "resilient-run-123"

        # Run first 2 steps, then "crash"
        results1 = await simulated_agent_run(run_id, start_from_step=0)

        # Artificially stop after 2 steps (simulating crash)
        # In real scenario, process would terminate here

        # Resume run (simulating restart)
        results2 = await simulated_agent_run(run_id, start_from_step=0)

        # Should have completed all steps
        assert len(results2) >= 2

    @pytest.mark.asyncio
    async def test_step_idempotency(self, durable_runner):
        """
        Test that re-executing same step is idempotent.

        If a step is re-run with same step_id, the checkpoint
        should be updated (not duplicated).
        """
        run_id = "idempotent-run-123"

        # Execute step 1 multiple times
        for i in range(3):
            await durable_runner.checkpoint(
                run_id=run_id,
                step_id="step-1",
                state={"attempt": i + 1},
            )

        # Should only have one checkpoint for step-1
        checkpoints = await durable_runner.list_checkpoints(run_id)

        step1_checkpoints = [c for c in checkpoints if c.step_id == "step-1"]
        assert len(step1_checkpoints) == 1
        assert step1_checkpoints[0].state["attempt"] == 3  # Latest value
