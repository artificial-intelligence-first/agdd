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
from typing import Any, Dict, Optional, cast

from magsag.storage.base import StorageBackend
from magsag.storage.models import RunSnapshotRecord
from magsag.storage.serialization import json_safe

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

    def __init__(self, storage_backend: Optional[StorageBackend] = None):
        """
        Initialize snapshot store.

        Args:
            storage_backend: Optional persistent storage backend
                            (uses file-based storage if None)
        """
        self.storage_backend = storage_backend
        self._snapshots: Dict[str, RunSnapshot] = {}  # In-memory cache
        self._initialized_runs: set[str] = set()
        self._run_init_lock = asyncio.Lock()

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

        # Ensure run metadata exists when using persistent storage
        await self.ensure_run_initialized(run_id, snapshot.metadata)

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
        if await self._ensure_backend():
            if self.storage_backend is not None:  # pragma: no cover - defensive check
                records = await self.storage_backend.list_run_snapshots(run_id)
                for record in records:
                    key = f"{record.run_id}:{record.step_id}"
                    if key not in self._snapshots:
                        self._snapshots[key] = self._snapshot_from_record(record)

        run_snapshots: list[RunSnapshot] = [
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

        memory_deleted = len(keys_to_delete)
        if await self._ensure_backend():
            if self.storage_backend is None:  # pragma: no cover
                storage_deleted = 0
            else:
                storage_deleted = await self.storage_backend.delete_run_snapshots(run_id)
            total_deleted = storage_deleted
            if storage_deleted < memory_deleted:
                total_deleted = memory_deleted
        else:
            total_deleted = memory_deleted

        logger.info(f"Deleted {total_deleted} snapshots for run {run_id}")

        return total_deleted

    async def _ensure_backend(self) -> bool:
        """Ensure persistent storage backend is available."""
        if self.storage_backend is not None:
            return True

        try:
            from magsag.storage import get_storage_backend

            self.storage_backend = await get_storage_backend()
            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Snapshot store backend unavailable: %s", exc)
            return False

    async def ensure_run_initialized(
        self,
        run_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Ensure a run record exists before persisting snapshots/events."""
        if not run_id:
            return

        if run_id in self._initialized_runs:
            return

        if not await self._ensure_backend():
            return

        backend = self.storage_backend
        if backend is None:
            return

        async with self._run_init_lock:
            if run_id in self._initialized_runs:
                return

            try:
                existing = await backend.get_run(run_id)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.debug("Snapshot store could not fetch run %s: %s", run_id, exc)
                existing = None

            if existing:
                self._initialized_runs.add(run_id)
                return

            agent_slug = self._extract_agent_slug(metadata)
            parent_run_id = self._extract_parent_run_id(metadata)
            tags = self._extract_tags(metadata)

            try:
                await backend.create_run(
                    run_id=run_id,
                    agent_slug=agent_slug,
                    parent_run_id=parent_run_id,
                    started_at=datetime.now(UTC),
                    status="running",
                    tags=tags,
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    "Snapshot store could not auto-create run %s: %s",
                    run_id,
                    exc,
                )
            else:
                self._initialized_runs.add(run_id)

    def _extract_agent_slug(self, metadata: Optional[Dict[str, Any]]) -> str:
        if not isinstance(metadata, dict):
            return "unknown"
        for key in ("agent_slug", "agent", "slug", "agent_id"):
            value = metadata.get(key)
            if isinstance(value, str) and value:
                return value
        return "unknown"

    def _extract_parent_run_id(self, metadata: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(metadata, dict):
            return None
        for key in ("parent_run_id", "parent"):
            value = metadata.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _extract_tags(self, metadata: Optional[Dict[str, Any]]) -> Optional[list[str]]:
        if not isinstance(metadata, dict):
            return None
        tags = metadata.get("tags")
        if isinstance(tags, list):
            cleaned = [str(tag) for tag in tags if isinstance(tag, str) and tag]
            return cleaned or None
        return None

    # Storage backend integration (placeholders)

    async def _persist_snapshot(self, snapshot: RunSnapshot) -> None:
        """Persist snapshot to storage backend (if available)."""
        if not await self._ensure_backend():
            return

        record = RunSnapshotRecord(
            snapshot_id=snapshot.snapshot_id,
            run_id=snapshot.run_id,
            step_id=snapshot.step_id,
            state=dict(snapshot.state),
            metadata=dict(snapshot.metadata),
            created_at=snapshot.created_at,
        )

        backend = self.storage_backend
        if backend is None:  # pragma: no cover - defensive fallback
            return
        await backend.upsert_run_snapshot(record)

    async def _load_latest_from_backend(self, run_id: str) -> Optional[RunSnapshot]:
        """Load latest snapshot from storage backend."""
        if not await self._ensure_backend():
            return None

        backend = self.storage_backend
        if backend is None:  # pragma: no cover - defensive fallback
            return None

        record = await backend.get_latest_run_snapshot(run_id)
        if record is None:
            return None

        snapshot = self._snapshot_from_record(record)
        self._snapshots[f"{snapshot.run_id}:{snapshot.step_id}"] = snapshot
        return snapshot

    async def _load_snapshot_from_backend(
        self, run_id: str, step_id: str
    ) -> Optional[RunSnapshot]:
        """Load specific snapshot from storage backend."""
        if not await self._ensure_backend():
            return None

        backend = self.storage_backend
        if backend is None:  # pragma: no cover - defensive fallback
            return None

        record = await backend.get_run_snapshot(run_id, step_id)
        if record is None:
            return None

        snapshot = self._snapshot_from_record(record)
        self._snapshots[f"{snapshot.run_id}:{snapshot.step_id}"] = snapshot
        return snapshot

    def _snapshot_from_record(self, record: RunSnapshotRecord) -> RunSnapshot:
        """Convert storage record into RunSnapshot instance."""
        return RunSnapshot(
            snapshot_id=record.snapshot_id,
            run_id=record.run_id,
            step_id=record.step_id,
            created_at=record.created_at,
            state=dict(record.state),
            metadata=dict(record.metadata),
        )

    # File-based storage fallback

    async def _save_to_file(self, snapshot: RunSnapshot) -> None:
        """Save snapshot to file (fallback when no backend available)."""
        snapshots_dir = Path(".magsag/snapshots") / snapshot.run_id
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
        snapshots_dir = Path(".magsag/snapshots") / run_id

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
        snapshot_file = Path(".magsag/snapshots") / run_id / f"{step_id}.json"

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
                return cast(Dict[str, Any], json.load(f))
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

        await self._record_event(
            run_id=run_id,
            agent_slug=self._resolve_agent_slug(metadata),
            event_type="run.snapshot.saved",
            message=f"Saved snapshot for step {step_id}",
            payload={
                "snapshot_id": snapshot.snapshot_id,
                "step_id": snapshot.step_id,
                "metadata": metadata or {},
            },
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

        await self._record_event(
            run_id=run_id,
            agent_slug=self._resolve_agent_slug(snapshot.metadata),
            event_type="run.resume",
            message=f"Resumed run {run_id} from step {snapshot.step_id}",
            payload={
                "snapshot_id": snapshot.snapshot_id,
                "step_id": snapshot.step_id,
            },
        )

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

    def _resolve_agent_slug(self, metadata: Optional[Dict[str, Any]]) -> str:
        """Extract agent slug from metadata when available."""
        if not metadata:
            return "unknown"
        for key in ("agent_slug", "agent"):
            value = metadata.get(key)
            if isinstance(value, str) and value:
                return value
        return "unknown"

    async def _record_event(
        self,
        *,
        run_id: str,
        agent_slug: str,
        event_type: str,
        message: Optional[str],
        payload: Dict[str, Any],
    ) -> None:
        """Append durable runner events to the storage backend."""
        storage = self.snapshot_store.storage_backend
        if storage is None:
            try:
                from magsag.storage import get_storage_backend

                storage = await get_storage_backend()
                self.snapshot_store.storage_backend = storage
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    "Durable runner could not initialize storage backend for events: %s",
                    exc,
                )
                return

        # Ensure run exists before recording event to satisfy FK constraints
        try:
            await self.snapshot_store.ensure_run_initialized(
                run_id,
                {"agent_slug": agent_slug},
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug(
                "Durable runner failed ensuring run %s before event %s: %s",
                run_id,
                event_type,
                exc,
            )

        try:
            safe_payload = cast(Dict[str, Any], json_safe(payload))
            await storage.append_event(
                run_id=run_id,
                agent_slug=agent_slug,
                event_type=event_type,
                timestamp=datetime.now(UTC),
                message=message,
                payload=safe_payload,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Failed to append durable runner event %s for run %s: %s",
                event_type,
                run_id,
                exc,
            )
