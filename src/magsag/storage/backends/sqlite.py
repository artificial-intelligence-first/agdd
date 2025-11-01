"""
SQLite storage backend with FTS5 full-text search support.

This is the default storage backend for development and small-scale deployments.
It provides zero-configuration local storage with optional full-text search.

For production deployments, consider PostgreSQL/TimescaleDB backend.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from magsag.storage.base import StorageBackend, StorageCapabilities
from magsag.storage.models import ApprovalTicketRecord, RunSnapshotRecord
from magsag.storage.serialization import json_safe


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
        db_path: str | Path = ".magsag/storage.db",
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
        """Initialize database schema with async support for blocking I/O"""
        # Create parent directory (sync operation, but fast)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Run blocking sqlite3.connect in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        self._conn = await loop.run_in_executor(None, self._connect_db)

        # Enable pragmas (run in executor to be safe)
        await loop.run_in_executor(None, self._configure_db)

        # Create schema
        await self._create_schema()

    def _connect_db(self) -> sqlite3.Connection:
        """Create SQLite connection (blocking operation for executor)"""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,  # Allow multi-threaded access
            isolation_level=None,  # Autocommit mode
        )
        conn.row_factory = sqlite3.Row  # Dict-like row access
        return conn

    def _configure_db(self) -> None:
        """Configure database pragmas (blocking operation for executor)"""
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging

    async def _create_schema(self) -> None:
        """Create database tables and indexes (async to avoid blocking event loop)"""
        if self._conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        # Run schema creation in executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._create_schema_blocking)

    def _create_schema_blocking(self) -> None:
        """Create database schema (blocking operation for executor)"""
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        # Runs table
        conn.execute(
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_agent_started ON runs(agent_slug, started_at DESC)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status, started_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_parent ON runs(parent_run_id)")

        # Events table
        conn.execute(
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_run_ts ON events(run_id, ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type, ts DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_slug, ts DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_span ON events(span_id)")

        # FTS5 virtual table for full-text search
        if self.enable_fts:
            # Check if FTS5 is available
            try:
                conn.execute("SELECT fts5_version()")

                # Create FTS5 virtual table
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS events_fts
                    USING fts5(msg, content='events', content_rowid='id')
                    """
                )

                # Triggers to keep FTS5 in sync
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
                        INSERT INTO events_fts(rowid, msg)
                        VALUES (new.id, COALESCE(new.msg, ''));
                    END
                    """
                )

                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
                        DELETE FROM events_fts WHERE rowid = old.id;
                    END
                    """
                )

                conn.execute(
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

        # v0.2 Enterprise Tables

        # Approvals table for approval-as-a-policy workflow
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                ticket_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                agent_slug TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                tool_args TEXT NOT NULL DEFAULT '{}',
                args_hash TEXT NOT NULL DEFAULT '',
                step_id TEXT,
                requested_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'denied', 'expired')),
                resolved_at TEXT,
                resolved_by TEXT,
                decision_reason TEXT,
                response TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_approvals_run ON approvals(run_id, requested_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status, expires_at)"
        )

        # Schema patching for new columns (idempotent ALTER TABLE operations)
        for ddl in (
            "ALTER TABLE approvals ADD COLUMN args_hash TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE approvals ADD COLUMN step_id TEXT",
            "ALTER TABLE approvals ADD COLUMN decision_reason TEXT",
            "ALTER TABLE approvals ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'",
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                # Column already exists
                pass

        # Snapshots table for durable run checkpoint/resume
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT '{}',
                metadata TEXT NOT NULL DEFAULT '{}',
                UNIQUE(run_id, step_id),
                FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_snapshots_run ON snapshots(run_id, created_at DESC)"
        )

        for ddl in (
            "ALTER TABLE snapshots ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'",
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                pass

        # Memory entries table for memory IR layer
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_entries (
                memory_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                agent_slug TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_run ON memory_entries(run_id, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_key ON memory_entries(agent_slug, key, created_at DESC)"
        )

        conn.commit()

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
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        conn.execute(
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
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        if started_at is None:
            started_at = datetime.now(timezone.utc)

        conn.execute(
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
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        updates: List[str] = []
        params: List[Any] = []

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
        allowed_fields = {"status", "ended_at", "metrics"}
        for assignment in updates:
            field = assignment.split("=", 1)[0].strip()
            if field not in allowed_fields:
                raise ValueError(f"Unexpected field in update: {field}")

        update_sql = "UPDATE runs SET " + ", ".join(updates) + " WHERE run_id = ?"  # nosec B608 - assignments use vetted column names
        conn.execute(update_sql, params)

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get run metadata"""
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        cursor = conn.execute(
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
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

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

        cursor = conn.execute(query, params)
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
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

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

        cursor = conn.execute(query, params)

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

    def _row_to_approval_record(self, row: sqlite3.Row) -> ApprovalTicketRecord:
        """Convert SQLite row into ApprovalTicketRecord."""
        return ApprovalTicketRecord(
            ticket_id=row["ticket_id"],
            run_id=row["run_id"],
            agent_slug=row["agent_slug"],
            tool_name=row["tool_name"],
            masked_args=json.loads(row["tool_args"]) if row["tool_args"] else {},
            args_hash=row["args_hash"],
            step_id=row["step_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            requested_at=datetime.fromisoformat(row["requested_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            status=row["status"],
            resolved_at=datetime.fromisoformat(row["resolved_at"])
            if row["resolved_at"]
            else None,
            resolved_by=row["resolved_by"],
            decision_reason=row["decision_reason"],
            response=json.loads(row["response"]) if row["response"] else None,
        )

    def _row_to_snapshot_record(self, row: sqlite3.Row) -> RunSnapshotRecord:
        """Convert SQLite row into RunSnapshotRecord."""
        return RunSnapshotRecord(
            snapshot_id=row["snapshot_id"],
            run_id=row["run_id"],
            step_id=row["step_id"],
            state=json.loads(row["state"]) if row["state"] else {},
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    async def create_approval_ticket(self, record: ApprovalTicketRecord) -> None:
        """Persist a new approval ticket (idempotent by ticket_id)."""
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        masked_args_json = json.dumps(json_safe(record.masked_args), ensure_ascii=False)
        response_payload = (
            json_safe(record.response) if record.response is not None else None
        )
        response_json = (
            json.dumps(response_payload, ensure_ascii=False)
            if response_payload is not None
            else None
        )
        metadata_json = json.dumps(json_safe(record.metadata), ensure_ascii=False)

        conn.execute(
            """
            INSERT INTO approvals (
                ticket_id,
                run_id,
                agent_slug,
                tool_name,
                tool_args,
                args_hash,
                step_id,
                requested_at,
                expires_at,
                status,
                resolved_at,
                resolved_by,
                decision_reason,
                response,
                metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticket_id) DO UPDATE SET
                run_id=excluded.run_id,
                agent_slug=excluded.agent_slug,
                tool_name=excluded.tool_name,
                tool_args=excluded.tool_args,
                args_hash=excluded.args_hash,
                step_id=excluded.step_id,
                requested_at=excluded.requested_at,
                expires_at=excluded.expires_at,
                status=excluded.status,
                resolved_at=excluded.resolved_at,
                resolved_by=excluded.resolved_by,
                decision_reason=excluded.decision_reason,
                response=excluded.response,
                metadata=excluded.metadata
            """,
            (
                record.ticket_id,
                record.run_id,
                record.agent_slug,
                record.tool_name,
                masked_args_json,
                record.args_hash,
                record.step_id,
                record.requested_at.astimezone(timezone.utc).isoformat(),
                record.expires_at.astimezone(timezone.utc).isoformat(),
                record.status,
                record.resolved_at.astimezone(timezone.utc).isoformat()
                if record.resolved_at
                else None,
                record.resolved_by,
                record.decision_reason,
                response_json,
                metadata_json,
            ),
        )

    async def update_approval_ticket(self, record: ApprovalTicketRecord) -> None:
        """Update an existing approval ticket."""
        await self.create_approval_ticket(record)

    async def get_approval_ticket(self, ticket_id: str) -> Optional[ApprovalTicketRecord]:
        """Retrieve an approval ticket by ID."""
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        cursor = conn.execute(
            """
            SELECT *
            FROM approvals
            WHERE ticket_id = ?
            """,
            (ticket_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return self._row_to_approval_record(row)

    async def list_approval_tickets(
        self,
        run_id: Optional[str] = None,
        agent_slug: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ApprovalTicketRecord]:
        """List approval tickets with optional filters."""
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        query = "SELECT * FROM approvals WHERE 1=1"
        params: List[Any] = []

        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)

        if agent_slug:
            query += " AND agent_slug = ?"
            params.append(agent_slug)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY requested_at ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        return [self._row_to_approval_record(row) for row in rows]

    async def upsert_run_snapshot(self, record: RunSnapshotRecord) -> None:
        """Persist a run snapshot (idempotent by run_id + step_id)."""
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        state_json = json.dumps(json_safe(record.state), ensure_ascii=False)
        metadata_json = json.dumps(json_safe(record.metadata), ensure_ascii=False)

        conn.execute(
            """
            INSERT INTO snapshots (
                snapshot_id,
                run_id,
                step_id,
                created_at,
                state,
                metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, step_id) DO UPDATE SET
                snapshot_id=excluded.snapshot_id,
                created_at=excluded.created_at,
                state=excluded.state,
                metadata=excluded.metadata
            """,
            (
                record.snapshot_id,
                record.run_id,
                record.step_id,
                record.created_at.astimezone(timezone.utc).isoformat(),
                state_json,
                metadata_json,
            ),
        )

    async def get_latest_run_snapshot(self, run_id: str) -> Optional[RunSnapshotRecord]:
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        cursor = conn.execute(
            """
            SELECT *
            FROM snapshots
            WHERE run_id = ?
            ORDER BY datetime(created_at) DESC
            LIMIT 1
            """,
            (run_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_snapshot_record(row)

    async def get_run_snapshot(self, run_id: str, step_id: str) -> Optional[RunSnapshotRecord]:
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        cursor = conn.execute(
            """
            SELECT * FROM snapshots
            WHERE run_id = ? AND step_id = ?
            LIMIT 1
            """,
            (run_id, step_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_snapshot_record(row)

    async def list_run_snapshots(self, run_id: str) -> List[RunSnapshotRecord]:
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        cursor = conn.execute(
            """
            SELECT *
            FROM snapshots
            WHERE run_id = ?
            ORDER BY datetime(created_at) ASC
            """,
            (run_id,),
        )
        rows = cursor.fetchall()
        return [self._row_to_snapshot_record(row) for row in rows]

    async def delete_run_snapshots(self, run_id: str) -> int:
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        cursor = conn.execute(
            "DELETE FROM snapshots WHERE run_id = ?",
            (run_id,),
        )
        return cursor.rowcount if cursor.rowcount is not None else 0

    async def search_text(
        self,
        query: str,
        agent_slug: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Full-text search across event messages using FTS5"""
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        if not self.enable_fts:
            raise NotImplementedError("Full-text search not available (FTS5 disabled)")

        # FTS5 query with JOIN to events table for filtering
        sql = """
            SELECT e.*
            FROM events_fts fts
            JOIN events e ON e.id = fts.rowid
            WHERE fts MATCH ?
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

        cursor = conn.execute(sql, params)
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
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = cutoff - timedelta(days=hot_days)
        cutoff_iso = cutoff.isoformat()

        # Count runs to be deleted
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM runs WHERE started_at < ?",
            (cutoff_iso,),
        )
        runs_to_delete = cursor.fetchone()["count"]

        # Count events to be deleted
        cursor = conn.execute(
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
        conn.execute(
            "DELETE FROM runs WHERE started_at < ?",
            (cutoff_iso,),
        )

        # VACUUM to reclaim space
        conn.execute("VACUUM")

        return {
            "dry_run": False,
            "runs_deleted": runs_to_delete,
            "events_deleted": events_to_delete,
            "cutoff": cutoff_iso,
        }
