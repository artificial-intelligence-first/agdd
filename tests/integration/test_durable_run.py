"""
Integration tests for Durable Run with snapshot/restore.

Tests the complete durable run lifecycle including:
- Snapshot creation at step boundaries
- State restoration
- Restart resilience
- Step-level idempotency
"""
import asyncio
import uuid
from pathlib import Path
from typing import Optional

import pytest

from magsag.runners.durable import DurableRunner, SnapshotStore
from magsag.storage.backends.sqlite import SQLiteStorageBackend

@pytest.fixture
def snapshot_store(tmp_path: Path) -> SnapshotStore:
    """Create snapshot store with temp directory."""
    return SnapshotStore(storage_backend=None)

@pytest.fixture
def durable_runner(snapshot_store: SnapshotStore) -> DurableRunner:
    """Create durable runner for testing."""
    return DurableRunner(snapshot_store=snapshot_store, enable_auto_snapshot=True)

class TestSnapshotStore:
    """Tests for SnapshotStore."""

    @pytest.mark.asyncio
    async def test_save_snapshot(self, snapshot_store: SnapshotStore) -> None:
        """Test saving a snapshot."""
        snapshot = await snapshot_store.save_snapshot(run_id='test-run-123', step_id='step-1', state={'counter': 1, 'data': 'test'}, metadata={'agent': 'test-agent'})
        assert snapshot.snapshot_id is not None
        assert snapshot.run_id == 'test-run-123'
        assert snapshot.step_id == 'step-1'
        assert snapshot.state == {'counter': 1, 'data': 'test'}
        assert snapshot.metadata == {'agent': 'test-agent'}
        assert snapshot.created_at is not None

    @pytest.mark.asyncio
    async def test_snapshot_idempotency(self, snapshot_store: SnapshotStore) -> None:
        """Test that saving same run_id + step_id is idempotent."""
        snapshot1 = await snapshot_store.save_snapshot(run_id='test-run-123', step_id='step-1', state={'counter': 1})
        snapshot2 = await snapshot_store.save_snapshot(run_id='test-run-123', step_id='step-1', state={'counter': 2})
        assert snapshot1.snapshot_id == snapshot2.snapshot_id
        assert snapshot2.state == {'counter': 2}

    @pytest.mark.asyncio
    async def test_get_latest_snapshot(self, snapshot_store: SnapshotStore) -> None:
        """Test retrieving latest snapshot."""
        await snapshot_store.save_snapshot(run_id='test-run-123', step_id='step-1', state={'counter': 1})
        await asyncio.sleep(0.01)
        await snapshot_store.save_snapshot(run_id='test-run-123', step_id='step-2', state={'counter': 2})
        latest = await snapshot_store.get_latest_snapshot('test-run-123')
        assert latest is not None
        assert latest.step_id == 'step-2'
        assert latest.state == {'counter': 2}

    @pytest.mark.asyncio
    async def test_get_snapshot_by_step(self, snapshot_store: SnapshotStore) -> None:
        """Test retrieving snapshot by step ID."""
        await snapshot_store.save_snapshot(run_id='test-run-123', step_id='step-1', state={'counter': 1})
        await snapshot_store.save_snapshot(run_id='test-run-123', step_id='step-2', state={'counter': 2})
        snapshot = await snapshot_store.get_snapshot_by_step(run_id='test-run-123', step_id='step-1')
        assert snapshot is not None
        assert snapshot.step_id == 'step-1'
        assert snapshot.state == {'counter': 1}

    @pytest.mark.asyncio
    async def test_list_snapshots(self, snapshot_store: SnapshotStore) -> None:
        """Test listing all snapshots for a run."""
        await snapshot_store.save_snapshot(run_id='test-run-123', step_id='step-1', state={'counter': 1})
        await snapshot_store.save_snapshot(run_id='test-run-123', step_id='step-2', state={'counter': 2})
        await snapshot_store.save_snapshot(run_id='test-run-456', step_id='step-1', state={'counter': 10})
        snapshots = await snapshot_store.list_snapshots('test-run-123')
        assert len(snapshots) == 2
        assert snapshots[0].step_id == 'step-1'
        assert snapshots[1].step_id == 'step-2'

    @pytest.mark.asyncio
    async def test_delete_snapshots(self, snapshot_store: SnapshotStore) -> None:
        """Test deleting all snapshots for a run."""
        await snapshot_store.save_snapshot(run_id='test-run-123', step_id='step-1', state={'counter': 1})
        await snapshot_store.save_snapshot(run_id='test-run-123', step_id='step-2', state={'counter': 2})
        count = await snapshot_store.delete_snapshots('test-run-123')
        assert count == 2
        snapshots = await snapshot_store.list_snapshots('test-run-123')
        assert len(snapshots) == 0

    @pytest.mark.asyncio
    async def test_snapshot_store_initializes_run_record(self, tmp_path: Path) -> None:
        """Ensure snapshot store creates run metadata when using a backend."""
        backend = SQLiteStorageBackend(db_path=tmp_path / 'snapshots.db', enable_fts=False)
        await backend.initialize()
        store = SnapshotStore(storage_backend=backend)
        run_id = f'backend-run-{uuid.uuid4().hex[:8]}'
        try:
            await store.save_snapshot(run_id=run_id, step_id='step-1', state={'value': 42}, metadata={'agent_slug': 'agent-backend'})
            run = await backend.get_run(run_id)
            assert run is not None
            assert run['agent_slug'] == 'agent-backend'
        finally:
            await backend.close()

class TestDurableRunner:
    """Tests for DurableRunner."""

    @pytest.mark.asyncio
    async def test_checkpoint(self, durable_runner: DurableRunner) -> None:
        """Test creating a checkpoint."""
        run_id = f'test-run-{uuid.uuid4().hex[:8]}'
        snapshot = await durable_runner.checkpoint(run_id=run_id, step_id='step-1', state={'progress': 0.5, 'items_processed': 10}, metadata={'agent': 'test-agent'})
        assert snapshot.run_id == run_id
        assert snapshot.step_id == 'step-1'
        assert snapshot.state['progress'] == 0.5

    @pytest.mark.asyncio
    async def test_resume_from_latest(self, durable_runner: DurableRunner) -> None:
        """Test resuming from latest checkpoint."""
        run_id = f'test-run-{uuid.uuid4().hex[:8]}'
        await durable_runner.checkpoint(run_id=run_id, step_id='step-1', state={'counter': 1})
        await durable_runner.checkpoint(run_id=run_id, step_id='step-2', state={'counter': 2})
        restored_state = await durable_runner.resume(run_id)
        assert restored_state is not None
        assert restored_state['counter'] == 2

    @pytest.mark.asyncio
    async def test_resume_from_specific_step(self, durable_runner: DurableRunner) -> None:
        """Test resuming from a specific step."""
        run_id = f'test-run-{uuid.uuid4().hex[:8]}'
        await durable_runner.checkpoint(run_id=run_id, step_id='step-1', state={'counter': 1})
        await durable_runner.checkpoint(run_id=run_id, step_id='step-2', state={'counter': 2})
        restored_state = await durable_runner.resume(run_id=run_id, from_step='step-1')
        assert restored_state is not None
        assert restored_state['counter'] == 1

    @pytest.mark.asyncio
    async def test_resume_no_snapshot(self, durable_runner: DurableRunner) -> None:
        """Test resuming when no snapshot exists."""
        restored_state = await durable_runner.resume(f'missing-run-{uuid.uuid4().hex[:8]}')
        assert restored_state is None

    @pytest.mark.asyncio
    async def test_list_checkpoints(self, durable_runner: DurableRunner) -> None:
        """Test listing checkpoints."""
        run_id = f'test-run-{uuid.uuid4().hex[:8]}'
        await durable_runner.checkpoint(run_id=run_id, step_id='step-1', state={'counter': 1})
        await durable_runner.checkpoint(run_id=run_id, step_id='step-2', state={'counter': 2})
        checkpoints = await durable_runner.list_checkpoints(run_id)
        assert len(checkpoints) == 2
        assert checkpoints[0].step_id == 'step-1'
        assert checkpoints[1].step_id == 'step-2'

    @pytest.mark.asyncio
    async def test_cleanup(self, durable_runner: DurableRunner) -> None:
        """Test cleaning up checkpoints."""
        run_id = f'test-run-{uuid.uuid4().hex[:8]}'
        await durable_runner.checkpoint(run_id=run_id, step_id='step-1', state={'counter': 1})
        count = await durable_runner.cleanup(run_id)
        assert count == 1
        checkpoints = await durable_runner.list_checkpoints(run_id)
        assert len(checkpoints) == 0

@pytest.mark.integration
@pytest.mark.slow
class TestDurableRunE2E:
    """End-to-end durable run tests."""

    @pytest.mark.asyncio
    async def test_restart_resilience(self, durable_runner: DurableRunner) -> None:
        """
        Test complete restart scenario.

        Simulates:
        1. Agent runs and saves checkpoints at each step
        2. Process crashes/restarts
        3. Agent resumes from last checkpoint
        4. Continues execution without redoing completed steps
        """

        async def simulated_agent_run(run_id: str, *, start_from_step: int=0, max_steps: Optional[int]=None) -> list[str]:
            """Simulate multi-step agent execution."""
            steps = ['init', 'process', 'validate', 'finalize']
            results: list[str] = []
            if start_from_step == 0:
                restored_state = await durable_runner.resume(run_id)
                if restored_state:
                    start_from_step = restored_state.get('last_step_index', 0) + 1
            for i in range(start_from_step, len(steps)):
                if max_steps is not None and i >= max_steps:
                    break
                step = steps[i]
                result = f'completed {step}'
                results.append(result)
                await durable_runner.checkpoint(run_id=run_id, step_id=step, state={'last_step_index': i, 'results': results})
            return results
        run_id = f'resilient-run-{uuid.uuid4().hex[:8]}'
        _first_run_results = await simulated_agent_run(run_id, start_from_step=0, max_steps=2)
        results2 = await simulated_agent_run(run_id, start_from_step=0)
        assert len(results2) >= 2

    @pytest.mark.asyncio
    async def test_step_idempotency(self, durable_runner: DurableRunner) -> None:
        """
        Test that re-executing same step is idempotent.

        If a step is re-run with same step_id, the checkpoint
        should be updated (not duplicated).
        """
        run_id = 'idempotent-run-123'
        for i in range(3):
            await durable_runner.checkpoint(run_id=run_id, step_id='step-1', state={'attempt': i + 1})
        checkpoints = await durable_runner.list_checkpoints(run_id)
        step1_checkpoints = [c for c in checkpoints if c.step_id == 'step-1']
        assert len(step1_checkpoints) == 1
        assert step1_checkpoints[0].state['attempt'] == 3
