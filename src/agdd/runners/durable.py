"""
Durable Run implementation with snapshot/restore capabilities.

Provides the ability to save and restore run state at step boundaries,
enabling restart resilience and step-level idempotency.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class RunSnapshot:
    """
    Snapshot of run state at a specific step.

    Captures all necessary information to resume execution from this point.
    """

    snapshot_id: str
    run_id: str
    step_id: str
    created_at: datetime
    state: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot to dictionary for storage."""
        return {
            "snapshot_id": self.snapshot_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "created_at": self.created_at.isoformat(),
            "state": self.state,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RunSnapshot:
        """Create snapshot from dictionary."""
        return cls(
            snapshot_id=data["snapshot_id"],
            run_id=data["run_id"],
            step_id=data["step_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            state=data.get("state", {}),
            metadata=data.get("metadata", {}),
        )


class SnapshotStore:
    """
    Storage backend for run snapshots.

    Provides methods to save and retrieve snapshots with idempotent writes.
    """

    def __init__(self, storage_backend: Optional[Any] = None):
        """
        Initialize snapshot store.

        Args:
            storage_backend: Optional persistent storage backend
                            (uses file-based storage if None)
        """
        self.storage_backend = storage_backend
        self._snapshots: Dict[str, RunSnapshot] = {}  # In-memory cache

    async def save_snapshot(
        self,
        run_id: str,
        step_id: str,
        state: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RunSnapshot:
        """
        Save a run snapshot (idempotent by run_id + step_id).

        If a snapshot with the same run_id and step_id already exists,
        it will be updated rather than duplicated.

        Args:
            run_id: Run identifier
            step_id: Step identifier (for idempotency)
            state: Current execution state to save
            metadata: Optional metadata

        Returns:
            Created or updated RunSnapshot
        """
        from uuid import uuid4

        # Generate snapshot key for idempotency
        snapshot_key = f"{run_id}:{step_id}"

        # Check if snapshot already exists (idempotency)
        if snapshot_key in self._snapshots:
            logger.info(f"Snapshot already exists for {snapshot_key}, updating")
            snapshot = self._snapshots[snapshot_key]
            snapshot.state = state
            snapshot.metadata = metadata or {}
        else:
            snapshot = RunSnapshot(
                snapshot_id=str(uuid4()),
                run_id=run_id,
                step_id=step_id,
                created_at=datetime.now(UTC),
                state=state,
                metadata=metadata or {},
            )
            self._snapshots[snapshot_key] = snapshot

        # Persist to storage backend if available
        if self.storage_backend:
            await self._persist_snapshot(snapshot)
        else:
            # File-based fallback
            await self._save_to_file(snapshot)

        logger.info(
            f"Saved snapshot {snapshot.snapshot_id} for run {run_id} at step {step_id}"
        )

        return snapshot

    async def get_latest_snapshot(self, run_id: str) -> Optional[RunSnapshot]:
        """
        Get the latest snapshot for a run.

        Args:
            run_id: Run identifier

        Returns:
            Latest RunSnapshot or None if no snapshots exist
        """
        # Find all snapshots for this run
        run_snapshots = [
            s for key, s in self._snapshots.items() if s.run_id == run_id
        ]

        if not run_snapshots:
            # Try to load from storage backend
            if self.storage_backend:
                return await self._load_latest_from_backend(run_id)
            # Try file-based fallback
            return await self._load_latest_from_file(run_id)

        # Return most recent snapshot
        return max(run_snapshots, key=lambda s: s.created_at)

    async def get_snapshot_by_step(
        self, run_id: str, step_id: str
    ) -> Optional[RunSnapshot]:
        """
        Get snapshot for a specific step.

        Args:
            run_id: Run identifier
            step_id: Step identifier

        Returns:
            RunSnapshot or None if not found
        """
        snapshot_key = f"{run_id}:{step_id}"
        snapshot = self._snapshots.get(snapshot_key)

        if snapshot:
            return snapshot

        # Try to load from storage backend
        if self.storage_backend:
            return await self._load_snapshot_from_backend(run_id, step_id)

        # Try file-based fallback
        return await self._load_snapshot_from_file(run_id, step_id)

    async def list_snapshots(self, run_id: str) -> list[RunSnapshot]:
        """
        List all snapshots for a run, sorted by creation time.

        Args:
            run_id: Run identifier

        Returns:
            List of RunSnapshots
        """
        run_snapshots = [
            s for key, s in self._snapshots.items() if s.run_id == run_id
        ]

        # Sort by creation time (oldest first)
        run_snapshots.sort(key=lambda s: s.created_at)

        return run_snapshots

    async def delete_snapshots(self, run_id: str) -> int:
        """
        Delete all snapshots for a run.

        Args:
            run_id: Run identifier

        Returns:
            Number of snapshots deleted
        """
        keys_to_delete = [key for key, s in self._snapshots.items() if s.run_id == run_id]

        for key in keys_to_delete:
            del self._snapshots[key]

        logger.info(f"Deleted {len(keys_to_delete)} snapshots for run {run_id}")

        return len(keys_to_delete)

    # Storage backend integration (placeholders)

    async def _persist_snapshot(self, snapshot: RunSnapshot) -> None:
        """Persist snapshot to storage backend (placeholder)."""
        # TODO: Implement storage backend integration
        pass

    async def _load_latest_from_backend(self, run_id: str) -> Optional[RunSnapshot]:
        """Load latest snapshot from storage backend (placeholder)."""
        # TODO: Implement storage backend integration
        return None

    async def _load_snapshot_from_backend(
        self, run_id: str, step_id: str
    ) -> Optional[RunSnapshot]:
        """Load specific snapshot from storage backend (placeholder)."""
        # TODO: Implement storage backend integration
        return None

    # File-based storage fallback

    async def _save_to_file(self, snapshot: RunSnapshot) -> None:
        """Save snapshot to file (fallback when no backend available)."""
        snapshots_dir = Path(".agdd/snapshots") / snapshot.run_id
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        snapshot_file = snapshots_dir / f"{snapshot.step_id}.json"

        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, self._write_snapshot_file, snapshot_file, snapshot
        )

    def _write_snapshot_file(self, path: Path, snapshot: RunSnapshot) -> None:
        """Blocking file write for executor."""
        with open(path, "w") as f:
            json.dump(snapshot.to_dict(), f, indent=2)

    async def _load_latest_from_file(self, run_id: str) -> Optional[RunSnapshot]:
        """Load latest snapshot from file (fallback)."""
        snapshots_dir = Path(".agdd/snapshots") / run_id

        if not snapshots_dir.exists():
            return None

        # Find all snapshot files
        snapshot_files = list(snapshots_dir.glob("*.json"))
        if not snapshot_files:
            return None

        # Sort by modification time (latest first)
        latest_file = max(snapshot_files, key=lambda f: f.stat().st_mtime)

        # Load snapshot
        loop = asyncio.get_event_loop()
        snapshot_data = await loop.run_in_executor(None, self._read_snapshot_file, latest_file)

        if snapshot_data:
            return RunSnapshot.from_dict(snapshot_data)

        return None

    async def _load_snapshot_from_file(
        self, run_id: str, step_id: str
    ) -> Optional[RunSnapshot]:
        """Load specific snapshot from file (fallback)."""
        snapshot_file = Path(".agdd/snapshots") / run_id / f"{step_id}.json"

        if not snapshot_file.exists():
            return None

        # Load snapshot
        loop = asyncio.get_event_loop()
        snapshot_data = await loop.run_in_executor(None, self._read_snapshot_file, snapshot_file)

        if snapshot_data:
            return RunSnapshot.from_dict(snapshot_data)

        return None

    def _read_snapshot_file(self, path: Path) -> Optional[Dict[str, Any]]:
        """Blocking file read for executor."""
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to read snapshot from {path}: {e}")
            return None


class DurableRunner:
    """
    Wrapper for agent runners that adds snapshot/restore capabilities.

    Provides step-level checkpointing and resume logic for resilient execution.
    """

    def __init__(
        self,
        snapshot_store: Optional[SnapshotStore] = None,
        enable_auto_snapshot: bool = True,
    ):
        """
        Initialize durable runner.

        Args:
            snapshot_store: Snapshot storage backend (creates default if None)
            enable_auto_snapshot: Automatically save snapshots at step boundaries
        """
        self.snapshot_store = snapshot_store or SnapshotStore()
        self.enable_auto_snapshot = enable_auto_snapshot

    async def checkpoint(
        self,
        run_id: str,
        step_id: str,
        state: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RunSnapshot:
        """
        Save a checkpoint at a step boundary.

        Args:
            run_id: Run identifier
            step_id: Step identifier
            state: Current execution state
            metadata: Optional metadata

        Returns:
            Created RunSnapshot
        """
        logger.info(f"Creating checkpoint for run {run_id} at step {step_id}")

        snapshot = await self.snapshot_store.save_snapshot(
            run_id=run_id,
            step_id=step_id,
            state=state,
            metadata=metadata,
        )

        return snapshot

    async def resume(
        self, run_id: str, from_step: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Resume execution from a snapshot.

        Args:
            run_id: Run identifier
            from_step: Optional step ID to resume from (uses latest if None)

        Returns:
            Restored state dict or None if no snapshot found
        """
        if from_step:
            logger.info(f"Resuming run {run_id} from step {from_step}")
            snapshot = await self.snapshot_store.get_snapshot_by_step(run_id, from_step)
        else:
            logger.info(f"Resuming run {run_id} from latest snapshot")
            snapshot = await self.snapshot_store.get_latest_snapshot(run_id)

        if snapshot is None:
            logger.warning(f"No snapshot found for run {run_id}")
            return None

        logger.info(
            f"Restored state from snapshot {snapshot.snapshot_id} "
            f"(step {snapshot.step_id}, created {snapshot.created_at})"
        )

        return snapshot.state

    async def list_checkpoints(self, run_id: str) -> list[RunSnapshot]:
        """
        List all checkpoints for a run.

        Args:
            run_id: Run identifier

        Returns:
            List of RunSnapshots
        """
        return await self.snapshot_store.list_snapshots(run_id)

    async def cleanup(self, run_id: str) -> int:
        """
        Clean up all snapshots for a run.

        Args:
            run_id: Run identifier

        Returns:
            Number of snapshots deleted
        """
        return await self.snapshot_store.delete_snapshots(run_id)
