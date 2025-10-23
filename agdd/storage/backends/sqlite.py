"""
SQLite storage backend with FTS5 full-text search support.

This is the default storage backend for development and small-scale deployments.
It provides zero-configuration local storage with optional full-text search.

For production deployments, consider PostgreSQL/TimescaleDB backend.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from agdd.storage.base import StorageBackend, StorageCapabilities


class SQLiteStorageBackend(StorageBackend):
    """
    SQLite-based storage backend with FTS5 full-text search.

    Features:
    - Zero configuration (single file database)
    - FTS5 full-text search on event messages
    - JSON support for flexible payloads
    - Suitable for local development and small deployments

    For production or when using Litestream for S3 replication:
    - Set db_path to a persistent location
    - Configure Litestream to replicate to S3/MinIO
    """

    def __init__(
        self,
        db_path: str | Path = ".agdd/storage.db",
        enable_fts: bool = True,
    ):
        """
        Initialize SQLite storage backend.

        Args:
            db_path: Path to SQLite database file
            enable_fts: Enable FTS5 full-text search (default: True)
        """
        self.db_path = Path(db_path)
        self.enable_fts = enable_fts
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def capabilities(self) -> StorageCapabilities:
        """Return capabilities supported by SQLite backend"""
        return StorageCapabilities(
            append_event=True,
            get_run=True,
            list_runs=True,
            query_metrics=False,  # Basic aggregation only
            search_text=self.enable_fts,
            vector_search=False,
            archive_artifacts=False,
            lifecycle_policy=False,
            streaming=True,
        )

    async def initialize(self) -> None:
        """Initialize database schema"""
        # Create parent directory
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Connect with proper settings
        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,  # Allow multi-threaded access
            isolation_level=None,  # Autocommit mode
        )
        self._conn.row_factory = sqlite3.Row  # Dict-like row access

        # Enable foreign keys
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging

        # Create schema
        await self._create_schema()

    async def _create_schema(self) -> None:
        """Create database tables and indexes"""
        assert self._conn is not None

        # Runs table
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                agent_slug TEXT NOT NULL,
                parent_run_id TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'canceled')),
                metrics TEXT NOT NULL DEFAULT '{}',
                tags TEXT NOT NULL DEFAULT '[]',
                FOREIGN KEY (parent_run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
            """
        )

        # Indexes on runs
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_agent_started ON runs(agent_slug, started_at DESC)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status, started_at DESC)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_parent ON runs(parent_run_id)"
        )

        # Events table
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                run_id TEXT NOT NULL,
                agent_slug TEXT NOT NULL,
                type TEXT NOT NULL,
                level TEXT,
                msg TEXT,
                payload TEXT NOT NULL DEFAULT '{}',
                span_id TEXT,
                parent_span_id TEXT,
                contract_id TEXT,
                contract_version TEXT,
                artifact_uri TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
            """
        )

        # Indexes on events
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_run_ts ON events(run_id, ts)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_type ON events(type, ts DESC)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_slug, ts DESC)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_span ON events(span_id)"
        )

        # FTS5 virtual table for full-text search
        if self.enable_fts:
            # Check if FTS5 is available
            try:
                self._conn.execute("SELECT fts5_version()")

                # Create FTS5 virtual table
                self._conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS events_fts
                    USING fts5(msg, content='events', content_rowid='id')
                    """
                )

                # Triggers to keep FTS5 in sync
                self._conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
                        INSERT INTO events_fts(rowid, msg)
                        VALUES (new.id, COALESCE(new.msg, ''));
                    END
                    """
                )

                self._conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
                        DELETE FROM events_fts WHERE rowid = old.id;
                    END
                    """
                )

                self._conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
                        DELETE FROM events_fts WHERE rowid = old.id;
                        INSERT INTO events_fts(rowid, msg)
                        VALUES (new.id, COALESCE(new.msg, ''));
                    END
                    """
                )
            except sqlite3.OperationalError:
                # FTS5 not available, disable it
                self.enable_fts = False

        self._conn.commit()

    async def close(self) -> None:
        """Close database connection"""
        if self._conn:
            self._conn.close()
            self._conn = None

    async def append_event(
        self,
        run_id: str,
        agent_slug: str,
        event_type: str,
        timestamp: datetime,
        level: Optional[str] = None,
        message: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        span_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        contract_id: Optional[str] = None,
        contract_version: Optional[str] = None,
    ) -> None:
        """Append an event to storage"""
        assert self._conn is not None

        self._conn.execute(
            """
            INSERT INTO events (
                ts, run_id, agent_slug, type, level, msg, payload,
                span_id, parent_span_id, contract_id, contract_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp.isoformat(),
                run_id,
                agent_slug,
                event_type,
                level,
                message,
                json.dumps(payload or {}),
                span_id,
                parent_span_id,
                contract_id,
                contract_version,
            ),
        )

    async def create_run(
        self,
        run_id: str,
        agent_slug: str,
        parent_run_id: Optional[str] = None,
        started_at: Optional[datetime] = None,
        status: str = "running",
        tags: Optional[List[str]] = None,
    ) -> None:
        """Create a new run record"""
        assert self._conn is not None

        if started_at is None:
            started_at = datetime.now(timezone.utc)

        self._conn.execute(
            """
            INSERT INTO runs (run_id, agent_slug, parent_run_id, started_at, status, tags)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                agent_slug,
                parent_run_id,
                started_at.isoformat(),
                status,
                json.dumps(tags or []),
            ),
        )

    async def update_run(
        self,
        run_id: str,
        status: Optional[str] = None,
        ended_at: Optional[datetime] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update run metadata"""
        assert self._conn is not None

        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)

        if ended_at is not None:
            updates.append("ended_at = ?")
            params.append(ended_at.isoformat())

        if metrics is not None:
            updates.append("metrics = ?")
            params.append(json.dumps(metrics))

        if not updates:
            return

        params.append(run_id)
        query = f"UPDATE runs SET {', '.join(updates)} WHERE run_id = ?"
        self._conn.execute(query, params)

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get run metadata"""
        assert self._conn is not None

        cursor = self._conn.execute(
            """
            SELECT run_id, agent_slug, parent_run_id, started_at, ended_at,
                   status, metrics, tags
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        return {
            "run_id": row["run_id"],
            "agent_slug": row["agent_slug"],
            "parent_run_id": row["parent_run_id"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "status": row["status"],
            "metrics": json.loads(row["metrics"]),
            "tags": json.loads(row["tags"]),
        }

    async def list_runs(
        self,
        agent_slug: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List runs with optional filters"""
        assert self._conn is not None

        query = "SELECT * FROM runs WHERE 1=1"
        params: List[Any] = []

        if agent_slug:
            query += " AND agent_slug = ?"
            params.append(agent_slug)

        if status:
            query += " AND status = ?"
            params.append(status)

        if since:
            query += " AND started_at >= ?"
            params.append(since.isoformat())

        if until:
            query += " AND started_at < ?"
            params.append(until.isoformat())

        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = self._conn.execute(query, params)
        rows = cursor.fetchall()

        return [
            {
                "run_id": row["run_id"],
                "agent_slug": row["agent_slug"],
                "parent_run_id": row["parent_run_id"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "status": row["status"],
                "metrics": json.loads(row["metrics"]),
                "tags": json.loads(row["tags"]),
            }
            for row in rows
        ]

    async def get_events(
        self,
        run_id: str,
        event_type: Optional[str] = None,
        level: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream events for a run"""
        assert self._conn is not None

        query = "SELECT * FROM events WHERE run_id = ?"
        params: List[Any] = [run_id]

        if event_type:
            query += " AND type = ?"
            params.append(event_type)

        if level:
            query += " AND level = ?"
            params.append(level)

        query += " ORDER BY ts ASC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor = self._conn.execute(query, params)

        for row in cursor:
            yield {
                "ts": row["ts"],
                "run_id": row["run_id"],
                "agent_slug": row["agent_slug"],
                "type": row["type"],
                "level": row["level"],
                "msg": row["msg"],
                "payload": json.loads(row["payload"]),
                "span_id": row["span_id"],
                "parent_span_id": row["parent_span_id"],
                "contract_id": row["contract_id"],
                "contract_version": row["contract_version"],
                "artifact_uri": row["artifact_uri"],
            }

    async def search_text(
        self,
        query: str,
        agent_slug: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Full-text search across event messages using FTS5"""
        assert self._conn is not None

        if not self.enable_fts:
            raise NotImplementedError("Full-text search not available (FTS5 disabled)")

        # FTS5 query with JOIN to events table for filtering
        sql = """
            SELECT e.*
            FROM events_fts fts
            JOIN events e ON e.id = fts.rowid
            WHERE events_fts MATCH ?
        """
        params: List[Any] = [query]

        if agent_slug:
            sql += " AND e.agent_slug = ?"
            params.append(agent_slug)

        if since:
            sql += " AND e.ts >= ?"
            params.append(since.isoformat())

        sql += " ORDER BY e.ts DESC LIMIT ?"
        params.append(limit)

        cursor = self._conn.execute(sql, params)
        rows = cursor.fetchall()

        return [
            {
                "ts": row["ts"],
                "run_id": row["run_id"],
                "agent_slug": row["agent_slug"],
                "type": row["type"],
                "level": row["level"],
                "msg": row["msg"],
                "payload": json.loads(row["payload"]),
                "span_id": row["span_id"],
                "parent_span_id": row["parent_span_id"],
                "contract_id": row["contract_id"],
                "contract_version": row["contract_version"],
                "artifact_uri": row["artifact_uri"],
            }
            for row in rows
        ]

    async def vacuum(
        self,
        hot_days: int = 7,
        max_disk_mb: Optional[int] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Clean up old data based on retention policy"""
        assert self._conn is not None

        cutoff = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        cutoff = cutoff - timedelta(days=hot_days)
        cutoff_iso = cutoff.isoformat()

        # Count runs to be deleted
        cursor = self._conn.execute(
            "SELECT COUNT(*) as count FROM runs WHERE started_at < ?",
            (cutoff_iso,),
        )
        runs_to_delete = cursor.fetchone()["count"]

        # Count events to be deleted
        cursor = self._conn.execute(
            "SELECT COUNT(*) as count FROM events WHERE ts < ?",
            (cutoff_iso,),
        )
        events_to_delete = cursor.fetchone()["count"]

        if dry_run:
            return {
                "dry_run": True,
                "runs_to_delete": runs_to_delete,
                "events_to_delete": events_to_delete,
                "cutoff": cutoff_iso,
            }

        # Delete old runs (cascade will delete events)
        self._conn.execute(
            "DELETE FROM runs WHERE started_at < ?",
            (cutoff_iso,),
        )

        # VACUUM to reclaim space
        self._conn.execute("VACUUM")

        return {
            "dry_run": False,
            "runs_deleted": runs_to_delete,
            "events_deleted": events_to_delete,
            "cutoff": cutoff_iso,
        }
