"""
Memory storage backends for the Memory IR layer.

Provides persistent storage for MemoryEntry objects with support for
TTL, PII tagging, semantic search, and retention policies.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from magsag.core.memory import MemoryEntry, MemoryScope


class AbstractMemoryStore(ABC):
    """
    Abstract base class for memory storage backends.

    Implementations provide persistent storage for memory entries with
    support for scoping, TTL, PII tagging, and efficient retrieval.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize storage (create tables, indexes, etc.)"""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close connections and cleanup resources"""
        ...

    @abstractmethod
    async def create_memory(self, entry: MemoryEntry) -> None:
        """
        Store a new memory entry.

        Args:
            entry: Memory entry to store

        Raises:
            ValueError: If memory_id already exists
        """
        ...

    @abstractmethod
    async def get_memory(self, memory_id: str) -> Optional[MemoryEntry]:
        """
        Retrieve a memory entry by ID.

        Args:
            memory_id: Memory identifier

        Returns:
            MemoryEntry or None if not found or expired
        """
        ...

    @abstractmethod
    async def update_memory(self, entry: MemoryEntry) -> None:
        """
        Update an existing memory entry.

        Args:
            entry: Memory entry with updated values

        Raises:
            ValueError: If memory_id does not exist
        """
        ...

    @abstractmethod
    async def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a memory entry.

        Args:
            memory_id: Memory identifier

        Returns:
            True if deleted, False if not found
        """
        ...

    @abstractmethod
    async def list_memories(
        self,
        scope: Optional[MemoryScope] = None,
        agent_slug: Optional[str] = None,
        run_id: Optional[str] = None,
        key: Optional[str] = None,
        tags: Optional[List[str]] = None,
        include_expired: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MemoryEntry]:
        """
        List memory entries with optional filters.

        Args:
            scope: Filter by memory scope
            agent_slug: Filter by agent slug
            run_id: Filter by run ID
            key: Filter by exact key match
            tags: Filter by tags (AND logic)
            include_expired: Include expired entries
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of matching memory entries
        """
        ...

    @abstractmethod
    async def search_memories(
        self,
        query: str,
        scope: Optional[MemoryScope] = None,
        agent_slug: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryEntry]:
        """
        Full-text search across memory keys and values.

        Args:
            query: Search query
            scope: Filter by memory scope
            agent_slug: Filter by agent slug
            limit: Maximum results

        Returns:
            List of matching memory entries
        """
        ...

    @abstractmethod
    async def expire_old_memories(self) -> int:
        """
        Delete expired memory entries based on TTL.

        Returns:
            Number of deleted entries
        """
        ...

    @abstractmethod
    async def vacuum(
        self,
        scope: Optional[MemoryScope] = None,
        older_than_days: int = 90,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Clean up old memory entries based on retention policy.

        Args:
            scope: Filter by memory scope (None = all scopes)
            older_than_days: Delete entries older than this many days
            dry_run: If True, only report what would be deleted

        Returns:
            Report of deleted entries
        """
        ...


class SQLiteMemoryStore(AbstractMemoryStore):
    """
    SQLite-based memory storage backend.

    Features:
    - Zero configuration (single file database)
    - FTS5 full-text search on memory keys and values
    - JSON support for flexible memory values
    - TTL and PII tag support
    - Suitable for local development and small deployments
    """

    def __init__(
        self,
        db_path: str | Path = ".magsag/memory.db",
        enable_fts: bool = True,
    ):
        """
        Initialize SQLite memory store.

        Args:
            db_path: Path to SQLite database file
            enable_fts: Enable FTS5 full-text search (default: True)
        """
        self.db_path = Path(db_path)
        self.enable_fts = enable_fts
        self._conn: Optional[sqlite3.Connection] = None

    async def initialize(self) -> None:
        """Initialize database schema"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        loop = asyncio.get_event_loop()
        self._conn = await loop.run_in_executor(None, self._connect_db)
        await loop.run_in_executor(None, self._configure_db)
        await self._create_schema()

    def _connect_db(self) -> sqlite3.Connection:
        """Create SQLite connection (blocking operation)"""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _configure_db(self) -> None:
        """Configure database pragmas"""
        if self._conn is None:
            raise RuntimeError("SQLite connection not initialized")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")

    async def _create_schema(self) -> None:
        """Create database schema"""
        if self._conn is None:
            raise RuntimeError("SQLite connection not initialized")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._create_tables)

    def _create_tables(self) -> None:
        """Create database tables (blocking operation)"""
        if self._conn is None:
            raise RuntimeError("SQLite connection not initialized")

        # Main memories table
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                scope TEXT NOT NULL,
                agent_slug TEXT NOT NULL,
                run_id TEXT,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                pii_tags TEXT NOT NULL,
                retention_policy TEXT,
                embedding TEXT,
                tags TEXT NOT NULL,
                metadata TEXT NOT NULL
            )
        """)

        # Indexes for efficient queries
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_agent_slug ON memories(agent_slug)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_run_id ON memories(run_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_expires_at ON memories(expires_at)"
        )

        # FTS5 virtual table for full-text search
        if self.enable_fts:
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    memory_id UNINDEXED,
                    key,
                    value,
                    content=memories,
                    content_rowid=rowid
                )
            """)

            # Triggers to keep FTS index in sync
            self._conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, memory_id, key, value)
                    VALUES (new.rowid, new.memory_id, new.key, new.value);
                END
            """)
            self._conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, memory_id, key, value)
                    VALUES('delete', old.rowid, old.memory_id, old.key, old.value);
                END
            """)
            self._conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, memory_id, key, value)
                    VALUES('delete', old.rowid, old.memory_id, old.key, old.value);
                    INSERT INTO memories_fts(rowid, memory_id, key, value)
                    VALUES (new.rowid, new.memory_id, new.key, new.value);
                END
            """)

    async def close(self) -> None:
        """Close database connection"""
        if self._conn:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._conn.close)
            self._conn = None

    def _entry_to_row(self, entry: MemoryEntry) -> tuple[Any, ...]:
        """Convert MemoryEntry to database row"""
        return (
            entry.memory_id,
            entry.scope.value,
            entry.agent_slug,
            entry.run_id,
            entry.key,
            json.dumps(entry.value),
            entry.created_at.isoformat(),
            entry.updated_at.isoformat(),
            entry.expires_at.isoformat() if entry.expires_at else None,
            json.dumps(entry.pii_tags),
            entry.retention_policy,
            json.dumps(entry.embedding) if entry.embedding else None,
            json.dumps(entry.tags),
            json.dumps(entry.metadata),
        )

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        """Convert database row to MemoryEntry"""
        return MemoryEntry(
            memory_id=row["memory_id"],
            scope=MemoryScope(row["scope"]),
            agent_slug=row["agent_slug"],
            run_id=row["run_id"],
            key=row["key"],
            value=json.loads(row["value"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            pii_tags=json.loads(row["pii_tags"]),
            retention_policy=row["retention_policy"],
            embedding=json.loads(row["embedding"]) if row["embedding"] else None,
            tags=json.loads(row["tags"]),
            metadata=json.loads(row["metadata"]),
        )

    async def create_memory(self, entry: MemoryEntry) -> None:
        """Store a new memory entry"""
        if self._conn is None:
            raise RuntimeError("SQLite connection not initialized")

        loop = asyncio.get_event_loop()

        def _insert() -> None:
            if self._conn is None:
                raise RuntimeError("SQLite connection not initialized")
            try:
                self._conn.execute(
                    """
                    INSERT INTO memories (
                        memory_id, scope, agent_slug, run_id, key, value,
                        created_at, updated_at, expires_at, pii_tags,
                        retention_policy, embedding, tags, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._entry_to_row(entry),
                )
            except sqlite3.IntegrityError as e:
                raise ValueError(f"Memory with ID {entry.memory_id} already exists") from e

        await loop.run_in_executor(None, _insert)

    async def get_memory(self, memory_id: str) -> Optional[MemoryEntry]:
        """Retrieve a memory entry by ID"""
        if self._conn is None:
            raise RuntimeError("SQLite connection not initialized")

        loop = asyncio.get_event_loop()

        def _select() -> Optional[sqlite3.Row]:
            if self._conn is None:
                raise RuntimeError("SQLite connection not initialized")
            cursor = self._conn.execute(
                "SELECT * FROM memories WHERE memory_id = ?",
                (memory_id,),
            )
            return cast(Optional[sqlite3.Row], cursor.fetchone())

        row = await loop.run_in_executor(None, _select)
        if row is None:
            return None

        entry = self._row_to_entry(row)
        if entry.is_expired():
            return None

        return entry

    async def update_memory(self, entry: MemoryEntry) -> None:
        """Update an existing memory entry"""
        if self._conn is None:
            raise RuntimeError("SQLite connection not initialized")

        entry.updated_at = datetime.now(UTC)
        loop = asyncio.get_event_loop()

        def _update() -> None:
            if self._conn is None:
                raise RuntimeError("SQLite connection not initialized")
            # Build update parameters explicitly (exclude memory_id and created_at)
            row = self._entry_to_row(entry)
            update_params = row[1:6] + row[7:]  # Skip memory_id (0) and created_at (6)
            cursor = self._conn.execute(
                """
                UPDATE memories SET
                    scope = ?, agent_slug = ?, run_id = ?, key = ?, value = ?,
                    updated_at = ?, expires_at = ?, pii_tags = ?,
                    retention_policy = ?, embedding = ?, tags = ?, metadata = ?
                WHERE memory_id = ?
                """,
                update_params + (entry.memory_id,),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Memory with ID {entry.memory_id} does not exist")

        await loop.run_in_executor(None, _update)

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory entry"""
        if self._conn is None:
            raise RuntimeError("SQLite connection not initialized")

        loop = asyncio.get_event_loop()

        def _delete() -> int:
            if self._conn is None:
                raise RuntimeError("SQLite connection not initialized")
            cursor = self._conn.execute(
                "DELETE FROM memories WHERE memory_id = ?",
                (memory_id,),
            )
            return cursor.rowcount

        rowcount = await loop.run_in_executor(None, _delete)
        return rowcount > 0

    async def list_memories(
        self,
        scope: Optional[MemoryScope] = None,
        agent_slug: Optional[str] = None,
        run_id: Optional[str] = None,
        key: Optional[str] = None,
        tags: Optional[List[str]] = None,
        include_expired: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MemoryEntry]:
        """List memory entries with optional filters"""
        if self._conn is None:
            raise RuntimeError("SQLite connection not initialized")

        loop = asyncio.get_event_loop()

        def _select() -> List[sqlite3.Row]:
            if self._conn is None:
                raise RuntimeError("SQLite connection not initialized")

            where_clauses = []
            params: List[Any] = []

            if scope is not None:
                where_clauses.append("scope = ?")
                params.append(scope.value)

            if agent_slug is not None:
                where_clauses.append("agent_slug = ?")
                params.append(agent_slug)

            if run_id is not None:
                where_clauses.append("run_id = ?")
                params.append(run_id)

            if key is not None:
                where_clauses.append("key = ?")
                params.append(key)

            if not include_expired:
                where_clauses.append("(expires_at IS NULL OR expires_at > ?)")
                params.append(datetime.now(UTC).isoformat())

            # Tags filter (AND logic)
            if tags:
                for tag in tags:
                    where_clauses.append("tags LIKE ?")
                    params.append(f'%"{tag}"%')

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            query = f"""
                SELECT * FROM memories
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])

            cursor = self._conn.execute(query, params)
            return cursor.fetchall()

        rows = await loop.run_in_executor(None, _select)
        return [self._row_to_entry(row) for row in rows]

    async def search_memories(
        self,
        query: str,
        scope: Optional[MemoryScope] = None,
        agent_slug: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryEntry]:
        """Full-text search across memory keys and values"""
        if self._conn is None:
            raise RuntimeError("SQLite connection not initialized")

        if not self.enable_fts:
            raise NotImplementedError("Full-text search is not enabled")

        loop = asyncio.get_event_loop()

        def _search() -> List[sqlite3.Row]:
            if self._conn is None:
                raise RuntimeError("SQLite connection not initialized")

            # Build WHERE clauses for filtering
            where_clauses = ["memories_fts MATCH ?"]
            params: List[Any] = [query]

            if scope is not None:
                where_clauses.append("memories.scope = ?")
                params.append(scope.value)

            if agent_slug is not None:
                where_clauses.append("memories.agent_slug = ?")
                params.append(agent_slug)

            where_clauses.append("(memories.expires_at IS NULL OR memories.expires_at > ?)")
            params.append(datetime.now(UTC).isoformat())

            where_sql = " AND ".join(where_clauses)
            query_sql = f"""
                SELECT memories.* FROM memories
                INNER JOIN memories_fts ON memories.rowid = memories_fts.rowid
                WHERE {where_sql}
                ORDER BY rank
                LIMIT ?
            """
            params.append(limit)

            cursor = self._conn.execute(query_sql, params)
            return cursor.fetchall()

        rows = await loop.run_in_executor(None, _search)
        return [self._row_to_entry(row) for row in rows]

    async def expire_old_memories(self) -> int:
        """Delete expired memory entries"""
        if self._conn is None:
            raise RuntimeError("SQLite connection not initialized")

        loop = asyncio.get_event_loop()

        def _delete() -> int:
            if self._conn is None:
                raise RuntimeError("SQLite connection not initialized")
            cursor = self._conn.execute(
                "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (datetime.now(UTC).isoformat(),),
            )
            return cursor.rowcount

        return await loop.run_in_executor(None, _delete)

    async def vacuum(
        self,
        scope: Optional[MemoryScope] = None,
        older_than_days: int = 90,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Clean up old memory entries"""
        if self._conn is None:
            raise RuntimeError("SQLite connection not initialized")

        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        loop = asyncio.get_event_loop()

        def _vacuum() -> Dict[str, Any]:
            if self._conn is None:
                raise RuntimeError("SQLite connection not initialized")

            where_clauses = ["created_at < ?"]
            params: List[Any] = [cutoff.isoformat()]

            if scope is not None:
                where_clauses.append("scope = ?")
                params.append(scope.value)

            where_sql = " AND ".join(where_clauses)

            # Count entries to be deleted
            cursor = self._conn.execute(
                f"SELECT COUNT(*) as count FROM memories WHERE {where_sql}",
                params,
            )
            count = cursor.fetchone()["count"]

            if not dry_run and count > 0:
                self._conn.execute(
                    f"DELETE FROM memories WHERE {where_sql}",
                    params,
                )

            return {
                "deleted_count": count if not dry_run else 0,
                "would_delete_count": count if dry_run else 0,
                "scope": scope.value if scope else "all",
                "older_than_days": older_than_days,
                "cutoff": cutoff.isoformat(),
            }

        return await loop.run_in_executor(None, _vacuum)


class PostgresMemoryStore(AbstractMemoryStore):
    """
    PostgreSQL-based memory storage backend.

    Features:
    - Full ACID compliance
    - pg_trgm for fuzzy text search
    - pgvector for semantic/vector search (if installed)
    - Suitable for production deployments
    """

    def __init__(self, dsn: str):
        """
        Initialize PostgreSQL memory store.

        Args:
            dsn: PostgreSQL connection string
        """
        self.dsn = dsn
        self._pool: Optional[Any] = None  # asyncpg pool

    async def initialize(self) -> None:
        """Initialize database schema"""
        try:
            import asyncpg
        except ImportError:
            raise RuntimeError(
                "asyncpg is required for PostgreSQL backend. "
                "Install with: pip install asyncpg"
            )

        self._pool = await asyncpg.create_pool(self.dsn)

        async with self._pool.acquire() as conn:
            # Enable extensions
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

            # Main memories table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    agent_slug TEXT NOT NULL,
                    run_id TEXT,
                    key TEXT NOT NULL,
                    value JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    expires_at TIMESTAMPTZ,
                    pii_tags TEXT[] NOT NULL DEFAULT '{}',
                    retention_policy TEXT,
                    embedding VECTOR,
                    tags TEXT[] NOT NULL DEFAULT '{}',
                    metadata JSONB NOT NULL DEFAULT '{}'
                )
            """)

            # Indexes
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_agent_slug ON memories(agent_slug)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_run_id ON memories(run_id)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_expires_at ON memories(expires_at)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_tags ON memories USING GIN(tags)"
            )

    async def close(self) -> None:
        """Close database connection pool"""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def create_memory(self, entry: MemoryEntry) -> None:
        """Store a new memory entry"""
        if self._pool is None:
            raise RuntimeError("PostgreSQL connection pool not initialized")

        async with self._pool.acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO memories (
                        memory_id, scope, agent_slug, run_id, key, value,
                        created_at, updated_at, expires_at, pii_tags,
                        retention_policy, embedding, tags, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    """,
                    entry.memory_id,
                    entry.scope.value,
                    entry.agent_slug,
                    entry.run_id,
                    entry.key,
                    json.dumps(entry.value),
                    entry.created_at,
                    entry.updated_at,
                    entry.expires_at,
                    entry.pii_tags,
                    entry.retention_policy,
                    entry.embedding,
                    entry.tags,
                    json.dumps(entry.metadata),
                )
            except Exception as e:
                if "duplicate key" in str(e):
                    raise ValueError(f"Memory with ID {entry.memory_id} already exists") from e
                raise

    async def get_memory(self, memory_id: str) -> Optional[MemoryEntry]:
        """Retrieve a memory entry by ID"""
        if self._pool is None:
            raise RuntimeError("PostgreSQL connection pool not initialized")

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM memories
                WHERE memory_id = $1
                AND (expires_at IS NULL OR expires_at > NOW())
                """,
                memory_id,
            )

        if row is None:
            return None

        return MemoryEntry(
            memory_id=row["memory_id"],
            scope=MemoryScope(row["scope"]),
            agent_slug=row["agent_slug"],
            run_id=row["run_id"],
            key=row["key"],
            value=json.loads(row["value"]) if isinstance(row["value"], str) else row["value"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
            pii_tags=list(row["pii_tags"]),
            retention_policy=row["retention_policy"],
            embedding=list(row["embedding"]) if row["embedding"] else None,
            tags=list(row["tags"]),
            metadata=json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"],
        )

    async def update_memory(self, entry: MemoryEntry) -> None:
        """Update an existing memory entry"""
        if self._pool is None:
            raise RuntimeError("PostgreSQL connection pool not initialized")

        entry.updated_at = datetime.now(UTC)

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE memories SET
                    scope = $2, agent_slug = $3, run_id = $4, key = $5, value = $6,
                    updated_at = $7, expires_at = $8, pii_tags = $9,
                    retention_policy = $10, embedding = $11, tags = $12, metadata = $13
                WHERE memory_id = $1
                """,
                entry.memory_id,
                entry.scope.value,
                entry.agent_slug,
                entry.run_id,
                entry.key,
                json.dumps(entry.value),
                entry.updated_at,
                entry.expires_at,
                entry.pii_tags,
                entry.retention_policy,
                entry.embedding,
                entry.tags,
                json.dumps(entry.metadata),
            )

            if result == "UPDATE 0":
                raise ValueError(f"Memory with ID {entry.memory_id} does not exist")

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory entry"""
        if self._pool is None:
            raise RuntimeError("PostgreSQL connection pool not initialized")

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM memories WHERE memory_id = $1",
                memory_id,
            )

        return cast(str, result) != "DELETE 0"

    async def list_memories(
        self,
        scope: Optional[MemoryScope] = None,
        agent_slug: Optional[str] = None,
        run_id: Optional[str] = None,
        key: Optional[str] = None,
        tags: Optional[List[str]] = None,
        include_expired: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MemoryEntry]:
        """List memory entries with optional filters"""
        if self._pool is None:
            raise RuntimeError("PostgreSQL connection pool not initialized")

        where_clauses = []
        params: List[Any] = []
        param_idx = 1

        if scope is not None:
            where_clauses.append(f"scope = ${param_idx}")
            params.append(scope.value)
            param_idx += 1

        if agent_slug is not None:
            where_clauses.append(f"agent_slug = ${param_idx}")
            params.append(agent_slug)
            param_idx += 1

        if run_id is not None:
            where_clauses.append(f"run_id = ${param_idx}")
            params.append(run_id)
            param_idx += 1

        if key is not None:
            where_clauses.append(f"key = ${param_idx}")
            params.append(key)
            param_idx += 1

        if not include_expired:
            where_clauses.append("(expires_at IS NULL OR expires_at > NOW())")

        if tags:
            where_clauses.append(f"tags @> ${param_idx}")
            params.append(tags)
            param_idx += 1

        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
        query = f"""
            SELECT * FROM memories
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [
            MemoryEntry(
                memory_id=row["memory_id"],
                scope=MemoryScope(row["scope"]),
                agent_slug=row["agent_slug"],
                run_id=row["run_id"],
                key=row["key"],
                value=json.loads(row["value"]) if isinstance(row["value"], str) else row["value"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                expires_at=row["expires_at"],
                pii_tags=list(row["pii_tags"]),
                retention_policy=row["retention_policy"],
                embedding=list(row["embedding"]) if row["embedding"] else None,
                tags=list(row["tags"]),
                metadata=json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"],
            )
            for row in rows
        ]

    async def search_memories(
        self,
        query: str,
        scope: Optional[MemoryScope] = None,
        agent_slug: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryEntry]:
        """Full-text search using pg_trgm"""
        if self._pool is None:
            raise RuntimeError("PostgreSQL connection pool not initialized")

        where_clauses = [
            "(key ILIKE $1 OR value::text ILIKE $1)",
            "(expires_at IS NULL OR expires_at > NOW())",
        ]
        params: List[Any] = [f"%{query}%"]
        param_idx = 2

        if scope is not None:
            where_clauses.append(f"scope = ${param_idx}")
            params.append(scope.value)
            param_idx += 1

        if agent_slug is not None:
            where_clauses.append(f"agent_slug = ${param_idx}")
            params.append(agent_slug)
            param_idx += 1

        where_sql = " AND ".join(where_clauses)
        query_sql = f"""
            SELECT * FROM memories
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ${param_idx}
        """
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query_sql, *params)

        return [
            MemoryEntry(
                memory_id=row["memory_id"],
                scope=MemoryScope(row["scope"]),
                agent_slug=row["agent_slug"],
                run_id=row["run_id"],
                key=row["key"],
                value=json.loads(row["value"]) if isinstance(row["value"], str) else row["value"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                expires_at=row["expires_at"],
                pii_tags=list(row["pii_tags"]),
                retention_policy=row["retention_policy"],
                embedding=list(row["embedding"]) if row["embedding"] else None,
                tags=list(row["tags"]),
                metadata=json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"],
            )
            for row in rows
        ]

    async def expire_old_memories(self) -> int:
        """Delete expired memory entries"""
        if self._pool is None:
            raise RuntimeError("PostgreSQL connection pool not initialized")

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= NOW()"
            )

        # Extract count from "DELETE N" result
        return int(result.split()[-1])

    async def vacuum(
        self,
        scope: Optional[MemoryScope] = None,
        older_than_days: int = 90,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Clean up old memory entries"""
        if self._pool is None:
            raise RuntimeError("PostgreSQL connection pool not initialized")

        where_clauses = [f"created_at < NOW() - INTERVAL '{older_than_days} days'"]
        params: List[Any] = []

        if scope is not None:
            where_clauses.append("scope = $1")
            params.append(scope.value)

        where_sql = " AND ".join(where_clauses)

        async with self._pool.acquire() as conn:
            # Count entries
            count_result = await conn.fetchval(
                f"SELECT COUNT(*) FROM memories WHERE {where_sql}",
                *params,
            )

            # Delete if not dry run
            if not dry_run and count_result > 0:
                await conn.execute(
                    f"DELETE FROM memories WHERE {where_sql}",
                    *params,
                )

        return {
            "deleted_count": count_result if not dry_run else 0,
            "would_delete_count": count_result if dry_run else 0,
            "scope": scope.value if scope else "all",
            "older_than_days": older_than_days,
        }
