"""
PostgreSQL / TimescaleDB storage backend for MAGSAG observability data.

Implements the StorageBackend interface using asyncpg with support for
JSONB payloads and full-text search via PostgreSQL's tsvector functions.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    TypeAlias,
)

from magsag.storage.base import StorageBackend, StorageCapabilities
from magsag.storage.models import ApprovalTicketRecord, RunSnapshotRecord
from magsag.storage.serialization import json_safe

try:  # pragma: no cover - optional dependency
    import asyncpg
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    asyncpg = None

if TYPE_CHECKING:  # pragma: no cover - typing aid
    from asyncpg import Pool, Record
    from asyncpg.connection import Connection
else:  # pragma: no cover - runtime fallback
    Connection = Any
    Pool = Any
    Record = Mapping[str, Any]


RunRow: TypeAlias = Record


class PostgresStorageBackend(StorageBackend):
    """PostgreSQL implementation of the MAGSAG storage backend."""

    def __init__(
        self,
        dsn: str,
        *,
        min_size: int = 1,
        max_size: int = 10,
        statement_timeout_ms: int = 30_000,
        search_language: str = "english",
    ) -> None:
        self.dsn = dsn
        self.min_size = min_size
        self.max_size = max_size
        self.statement_timeout_ms = statement_timeout_ms
        self.search_language = search_language
        if asyncpg is None:  # pragma: no cover - handled at runtime
            raise RuntimeError(
                "PostgreSQL backend requires the 'asyncpg' package. "
                "Install extras with `pip install magsag[postgres]`."
            )
        self._pool: Pool | None = None

    @property
    def capabilities(self) -> StorageCapabilities:
        """Advertise capabilities supported by the PostgreSQL backend."""
        return StorageCapabilities(
            append_event=True,
            get_run=True,
            list_runs=True,
            query_metrics=False,
            search_text=True,
            vector_search=False,
            archive_artifacts=False,
            lifecycle_policy=False,
            streaming=True,
        )

    async def initialize(self) -> None:
        """Initialize connection pool and database schema."""
        self._pool = await asyncpg.create_pool(
            dsn=self.dsn,
            min_size=self.min_size,
            max_size=self.max_size,
            command_timeout=self.statement_timeout_ms / 1000,
        )

        async with self._acquire() as conn:
            await conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE")

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    agent_slug TEXT NOT NULL,
                    parent_run_id TEXT REFERENCES runs(run_id) ON DELETE CASCADE,
                    started_at TIMESTAMPTZ NOT NULL,
                    ended_at TIMESTAMPTZ,
                    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'canceled')),
                    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
                    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
                )
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runs_agent_started
                    ON runs (agent_slug, started_at DESC)
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runs_status_started
                    ON runs (status, started_at DESC)
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id BIGSERIAL PRIMARY KEY,
                    ts TIMESTAMPTZ NOT NULL,
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    agent_slug TEXT NOT NULL,
                    type TEXT NOT NULL,
                    level TEXT,
                    msg TEXT,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    span_id TEXT,
                    parent_span_id TEXT,
                    contract_id TEXT,
                    contract_version TEXT,
                    artifact_uri TEXT
                )
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_events_run_ts
                    ON events (run_id, ts)
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_events_agent_ts
                    ON events (agent_slug, ts DESC)
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_events_span
                    ON events (span_id)
                """
            )
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_events_msg_search
                    ON events USING GIN (to_tsvector('{self.search_language}', coalesce(msg, '')))
                """
            )

            # v0.2 Enterprise Tables

            # Approvals table for approval-as-a-policy workflow
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS approvals (
                    ticket_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    agent_slug TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_args JSONB NOT NULL DEFAULT '{}'::jsonb,
                    args_hash TEXT NOT NULL DEFAULT '',
                    step_id TEXT,
                    requested_at TIMESTAMPTZ NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'denied', 'expired')),
                    resolved_at TIMESTAMPTZ,
                    resolved_by TEXT,
                    decision_reason TEXT,
                    response JSONB,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
                )
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_approvals_run
                    ON approvals (run_id, requested_at DESC)
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_approvals_status
                    ON approvals (status, expires_at)
                """
            )

            await conn.execute(
                "ALTER TABLE approvals ADD COLUMN IF NOT EXISTS args_hash TEXT NOT NULL DEFAULT ''"
            )
            await conn.execute(
                "ALTER TABLE approvals ADD COLUMN IF NOT EXISTS step_id TEXT"
            )
            await conn.execute(
                "ALTER TABLE approvals ADD COLUMN IF NOT EXISTS decision_reason TEXT"
            )
            await conn.execute(
                "ALTER TABLE approvals ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb"
            )

            # Snapshots table for durable run checkpoint/resume
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    step_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    state JSONB NOT NULL DEFAULT '{}'::jsonb,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    UNIQUE(run_id, step_id)
                )
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_snapshots_run
                    ON snapshots (run_id, created_at DESC)
                """
            )

            await conn.execute(
                "ALTER TABLE snapshots ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb"
            )

            # Memory entries table for memory IR layer
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_entries (
                    memory_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    agent_slug TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    expires_at TIMESTAMPTZ,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
                )
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_run
                    ON memory_entries (run_id, created_at DESC)
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_key
                    ON memory_entries (agent_slug, key, created_at DESC)
                """
            )

    async def close(self) -> None:
        """Terminate pool connections."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @asynccontextmanager
    async def _acquire(self) -> AsyncIterator[Connection]:
        if self._pool is None:
            raise RuntimeError("PostgreSQL backend not initialized")
        async with self._pool.acquire() as conn:
            await conn.execute(f"SET statement_timeout = {self.statement_timeout_ms}")
            yield conn

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
        data = {
            "run_id": run_id,
            "agent_slug": agent_slug,
            "type": event_type,
            "ts": timestamp,
            "level": level,
            "msg": message,
            "payload": payload or {},
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "contract_id": contract_id,
            "contract_version": contract_version,
        }
        async with self._acquire() as conn:
            await conn.execute(
                """
                INSERT INTO events (
                    run_id,
                    agent_slug,
                    type,
                    ts,
                    level,
                    msg,
                    payload,
                    span_id,
                    parent_span_id,
                    contract_id,
                    contract_version
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6,
                    COALESCE($7, '{}'::jsonb),
                    $8, $9, $10, $11
                )
                """,
                data["run_id"],
                data["agent_slug"],
                data["type"],
                data["ts"],
                data["level"],
                data["msg"],
                data["payload"],
                data["span_id"],
                data["parent_span_id"],
                data["contract_id"],
                data["contract_version"],
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
        started = started_at or datetime.now(timezone.utc)
        tags_array: Iterable[str] = tags or []
        async with self._acquire() as conn:
            await conn.execute(
                """
                INSERT INTO runs (
                    run_id,
                    agent_slug,
                    parent_run_id,
                    started_at,
                    status,
                    tags
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (run_id) DO NOTHING
                """,
                run_id,
                agent_slug,
                parent_run_id,
                started,
                status,
                list(tags_array),
            )

    async def update_run(
        self,
        run_id: str,
        status: Optional[str] = None,
        ended_at: Optional[datetime] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        assignments: List[str] = []
        params: List[Any] = []
        if status is not None:
            assignments.append("status = $" + str(len(params) + 1))
            params.append(status)
        if ended_at is not None:
            assignments.append("ended_at = $" + str(len(params) + 1))
            params.append(ended_at)
        if metrics is not None:
            assignments.append("metrics = $" + str(len(params) + 1))
            params.append(metrics)

        if not assignments:
            return

        allowed_assignments = {"status", "ended_at", "metrics"}
        for assignment in assignments:
            field = assignment.split("=", 1)[0].strip()
            if field not in allowed_assignments:
                raise ValueError(f"Unexpected column in update: {field}")

        params.append(run_id)
        async with self._acquire() as conn:
            await conn.execute(
                f"UPDATE runs SET {', '.join(assignments)} WHERE run_id = ${len(params)}",  # nosec B608 - update assignments restricted to allowlist
                *params,
            )

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        async with self._acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM runs WHERE run_id = $1", run_id)
            if row is None:
                return None
            return self._format_run(row)

    async def list_runs(
        self,
        agent_slug: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        conditions: List[str] = []
        params: List[Any] = []

        if agent_slug:
            conditions.append(f"agent_slug = ${len(params) + 1}")
            params.append(agent_slug)
        if status:
            conditions.append(f"status = ${len(params) + 1}")
            params.append(status)
        if since:
            conditions.append(f"started_at >= ${len(params) + 1}")
            params.append(since)
        if until:
            conditions.append(f"started_at < ${len(params) + 1}")
            params.append(until)

        params.extend([limit, offset])
        query_parts = ["SELECT *", "FROM runs"]
        if conditions:
            query_parts.append("WHERE " + " AND ".join(conditions))
        query_parts.append(
            f"ORDER BY started_at DESC LIMIT ${len(params) - 1} OFFSET ${len(params)}"
        )
        query = "\n".join(query_parts)

        async with self._acquire() as conn:
            rows = await conn.fetch(query, *params)  # nosec B608 - WHERE clause assembled from fixed column comparisons
        return [self._format_run(row) for row in rows]

    def _format_run(self, row: RunRow) -> Dict[str, Any]:
        metrics = row["metrics"] or {}
        tags = row["tags"] or []
        return {
            "run_id": row["run_id"],
            "agent_slug": row["agent_slug"],
            "parent_run_id": row["parent_run_id"],
            "started_at": row["started_at"].isoformat() if row["started_at"] else None,
            "ended_at": row["ended_at"].isoformat() if row["ended_at"] else None,
            "status": row["status"],
            "metrics": metrics if isinstance(metrics, dict) else {},
            "tags": list(tags) if isinstance(tags, (list, tuple)) else [],
        }

    def _row_to_approval_record(self, row: Mapping[str, Any]) -> ApprovalTicketRecord:
        """Convert database row into ApprovalTicketRecord."""
        masked_args = row["tool_args"] if isinstance(row["tool_args"], dict) else {}
        metadata = row["metadata"] if isinstance(row.get("metadata"), dict) else {}
        response = row["response"] if isinstance(row.get("response"), dict) else row.get("response")
        return ApprovalTicketRecord(
            ticket_id=row["ticket_id"],
            run_id=row["run_id"],
            agent_slug=row["agent_slug"],
            tool_name=row["tool_name"],
            masked_args=masked_args,
            args_hash=row["args_hash"],
            step_id=row.get("step_id"),
            metadata=metadata,
            requested_at=row["requested_at"],
            expires_at=row["expires_at"],
            status=row["status"],
            resolved_at=row.get("resolved_at"),
            resolved_by=row.get("resolved_by"),
            decision_reason=row.get("decision_reason"),
            response=response,
        )

    def _row_to_snapshot_record(self, row: Mapping[str, Any]) -> RunSnapshotRecord:
        state = row["state"] if isinstance(row.get("state"), dict) else {}
        metadata = row["metadata"] if isinstance(row.get("metadata"), dict) else {}
        return RunSnapshotRecord(
            snapshot_id=row["snapshot_id"],
            run_id=row["run_id"],
            step_id=row["step_id"],
            state=state,
            metadata=metadata,
            created_at=row["created_at"],
        )

    async def create_approval_ticket(self, record: ApprovalTicketRecord) -> None:
        """Persist a new approval ticket (idempotent)."""
        payload = {
            "ticket_id": record.ticket_id,
            "run_id": record.run_id,
            "agent_slug": record.agent_slug,
            "tool_name": record.tool_name,
            "tool_args": json_safe(record.masked_args),
            "args_hash": record.args_hash,
            "step_id": record.step_id,
            "requested_at": record.requested_at,
            "expires_at": record.expires_at,
            "status": record.status,
            "resolved_at": record.resolved_at,
            "resolved_by": record.resolved_by,
            "decision_reason": record.decision_reason,
            "response": json_safe(record.response) if record.response is not None else None,
            "metadata": json_safe(record.metadata),
        }
        async with self._acquire() as conn:
            await conn.execute(
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
                ) VALUES (
                    $1, $2, $3, $4, COALESCE($5, '{}'::jsonb), $6, $7,
                    $8, $9, $10, $11, $12, $13, $14, COALESCE($15, '{}'::jsonb)
                )
                ON CONFLICT (ticket_id) DO UPDATE SET
                    run_id = EXCLUDED.run_id,
                    agent_slug = EXCLUDED.agent_slug,
                    tool_name = EXCLUDED.tool_name,
                    tool_args = EXCLUDED.tool_args,
                    args_hash = EXCLUDED.args_hash,
                    step_id = EXCLUDED.step_id,
                    requested_at = EXCLUDED.requested_at,
                    expires_at = EXCLUDED.expires_at,
                    status = EXCLUDED.status,
                    resolved_at = EXCLUDED.resolved_at,
                    resolved_by = EXCLUDED.resolved_by,
                    decision_reason = EXCLUDED.decision_reason,
                    response = EXCLUDED.response,
                    metadata = EXCLUDED.metadata
                """,
                payload["ticket_id"],
                payload["run_id"],
                payload["agent_slug"],
                payload["tool_name"],
                payload["tool_args"],
                payload["args_hash"],
                payload["step_id"],
                payload["requested_at"],
                payload["expires_at"],
                payload["status"],
                payload["resolved_at"],
                payload["resolved_by"],
                payload["decision_reason"],
                payload["response"],
                payload["metadata"],
            )

    async def update_approval_ticket(self, record: ApprovalTicketRecord) -> None:
        """Update an existing approval ticket."""
        await self.create_approval_ticket(record)

    async def get_approval_ticket(self, ticket_id: str) -> Optional[ApprovalTicketRecord]:
        """Fetch approval ticket by ID."""
        async with self._acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM approvals WHERE ticket_id = $1", ticket_id)
            if row is None:
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
        """List approval tickets with filters."""
        conditions: List[str] = []
        params: List[Any] = []

        if run_id:
            conditions.append(f"run_id = ${len(params) + 1}")
            params.append(run_id)
        if agent_slug:
            conditions.append(f"agent_slug = ${len(params) + 1}")
            params.append(agent_slug)
        if status:
            conditions.append(f"status = ${len(params) + 1}")
            params.append(status)

        params.extend([limit, offset])
        query_parts = ["SELECT *", "FROM approvals"]
        if conditions:
            query_parts.append("WHERE " + " AND ".join(conditions))
        query_parts.append(
            f"ORDER BY requested_at ASC LIMIT ${len(params) - 1} OFFSET ${len(params)}"
        )
        query = "\n".join(query_parts)

        async with self._acquire() as conn:
            rows = await conn.fetch(query, *params)  # nosec B608 - predicates built from fixed columns
        return [self._row_to_approval_record(row) for row in rows]

    async def upsert_run_snapshot(self, record: RunSnapshotRecord) -> None:
        payload = {
            "snapshot_id": record.snapshot_id,
            "run_id": record.run_id,
            "step_id": record.step_id,
            "created_at": record.created_at,
            "state": json_safe(record.state),
            "metadata": json_safe(record.metadata),
        }
        async with self._acquire() as conn:
            await conn.execute(
                """
                INSERT INTO snapshots (
                    snapshot_id,
                    run_id,
                    step_id,
                    created_at,
                    state,
                    metadata
                ) VALUES (
                    $1, $2, $3, $4,
                    COALESCE($5, '{}'::jsonb),
                    COALESCE($6, '{}'::jsonb)
                )
                ON CONFLICT (run_id, step_id) DO UPDATE SET
                    snapshot_id = EXCLUDED.snapshot_id,
                    created_at = EXCLUDED.created_at,
                    state = EXCLUDED.state,
                    metadata = EXCLUDED.metadata
                """,
                payload["snapshot_id"],
                payload["run_id"],
                payload["step_id"],
                payload["created_at"],
                payload["state"],
                payload["metadata"],
            )

    async def get_latest_run_snapshot(self, run_id: str) -> Optional[RunSnapshotRecord]:
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM snapshots
                WHERE run_id = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                run_id,
            )
            if row is None:
                return None
            return self._row_to_snapshot_record(row)

    async def get_run_snapshot(self, run_id: str, step_id: str) -> Optional[RunSnapshotRecord]:
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM snapshots
                WHERE run_id = $1 AND step_id = $2
                LIMIT 1
                """,
                run_id,
                step_id,
            )
            if row is None:
                return None
            return self._row_to_snapshot_record(row)

    async def list_run_snapshots(self, run_id: str) -> List[RunSnapshotRecord]:
        async with self._acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM snapshots
                WHERE run_id = $1
                ORDER BY created_at ASC
                """,
                run_id,
            )
        return [self._row_to_snapshot_record(row) for row in rows]

    async def delete_run_snapshots(self, run_id: str) -> int:
        async with self._acquire() as conn:
            rows = await conn.fetch(
                "DELETE FROM snapshots WHERE run_id = $1 RETURNING 1",
                run_id,
            )
        return len(rows)

    def get_events(
        self,
        run_id: str,
        event_type: Optional[str] = None,
        level: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        async def _generator() -> AsyncIterator[Dict[str, Any]]:
            conditions = ["run_id = $1"]
            params: List[Any] = [run_id]

            if event_type:
                conditions.append(f"type = ${len(params) + 1}")
                params.append(event_type)
            if level:
                conditions.append(f"level = ${len(params) + 1}")
                params.append(level)

            limit_clause = f" LIMIT ${len(params) + 1}" if limit is not None else ""
            if limit is not None:
                params.append(limit)

            query_parts = [
                "SELECT *",
                "FROM events",
                "WHERE " + " AND ".join(conditions),
                "ORDER BY ts ASC" + limit_clause,
            ]
            query = "\n".join(query_parts)

            async with self._acquire() as conn:
                rows = await conn.fetch(query, *params)  # nosec B608 - query built from fixed predicates and positional parameters

            for row in rows:
                payload = row["payload"] if isinstance(row["payload"], dict) else {}
                yield {
                    "ts": row["ts"].isoformat(),
                    "run_id": row["run_id"],
                    "agent_slug": row["agent_slug"],
                    "type": row["type"],
                    "level": row["level"],
                    "msg": row["msg"],
                    "payload": payload,
                    "span_id": row["span_id"],
                    "parent_span_id": row["parent_span_id"],
                    "contract_id": row["contract_id"],
                    "contract_version": row["contract_version"],
                    "artifact_uri": row["artifact_uri"],
                }

        return _generator()

    async def search_text(
        self,
        query: str,
        agent_slug: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        params: List[Any] = [query]
        conditions = [
            f"to_tsvector('{self.search_language}', coalesce(msg, '')) @@ plainto_tsquery('{self.search_language}', $1)"
        ]

        if agent_slug:
            conditions.append(f"agent_slug = ${len(params) + 1}")
            params.append(agent_slug)
        if since:
            conditions.append(f"ts >= ${len(params) + 1}")
            params.append(since)

        params.append(limit)

        query_parts = [
            "SELECT *",
            "FROM events",
            "WHERE " + " AND ".join(conditions),
            f"ORDER BY ts DESC LIMIT ${len(params)}",
        ]
        query_sql = "\n".join(query_parts)

        async with self._acquire() as conn:
            rows = await conn.fetch(query_sql, *params)  # nosec B608 - query components use fixed column names and parameter placeholders

        return [
            {
                "ts": row["ts"].isoformat(),
                "run_id": row["run_id"],
                "agent_slug": row["agent_slug"],
                "type": row["type"],
                "level": row["level"],
                "msg": row["msg"],
                "payload": row["payload"] if isinstance(row["payload"], dict) else {},
                "span_id": row["span_id"],
                "parent_span_id": row["parent_span_id"],
                "contract_id": row["contract_id"],
                "contract_version": row["contract_version"],
                "artifact_uri": row["artifact_uri"],
            }
            for row in rows
        ]
