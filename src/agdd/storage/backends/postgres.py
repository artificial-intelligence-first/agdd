"""
PostgreSQL / TimescaleDB storage backend for AGDD observability data.

Implements the StorageBackend interface using asyncpg with support for
JSONB payloads and full-text search via PostgreSQL's tsvector functions.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, Iterable, List, Optional

from agdd.storage.base import StorageBackend, StorageCapabilities

try:  # pragma: no cover - optional dependency
    import asyncpg  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    asyncpg = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover - typing aid
    from asyncpg import Connection, Pool, Record  # type: ignore
else:
    Connection = Any  # type: ignore[misc]
    Pool = Any  # type: ignore[misc]
    Record = Any  # type: ignore[misc]


RunRow = Record


class PostgresStorageBackend(StorageBackend):
    """PostgreSQL implementation of the AGDD storage backend."""

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
                "Install extras with `pip install agdd[postgres]`."
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

        params.append(run_id)
        async with self._acquire() as conn:
            await conn.execute(
                f"UPDATE runs SET {', '.join(assignments)} WHERE run_id = ${len(params)}",
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

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])

        async with self._acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT *
                FROM runs
                {where_clause}
                ORDER BY started_at DESC
                LIMIT ${len(params) - 1}
                OFFSET ${len(params)}
                """,
                *params,
            )
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

            where_clause = " AND ".join(conditions)
            limit_clause = f" LIMIT ${len(params) + 1}" if limit is not None else ""
            if limit is not None:
                params.append(limit)

            async with self._acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT *
                    FROM events
                    WHERE {where_clause}
                    ORDER BY ts ASC
                    {limit_clause}
                    """,
                    *params,
                )

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

        async with self._acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT *
                FROM events
                WHERE {' AND '.join(conditions)}
                ORDER BY ts DESC
                LIMIT ${len(params)}
                """,
                *params,
            )

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
