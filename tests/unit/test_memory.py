"""Unit tests for Memory IR layer."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator

import pytest

from agdd.core.memory import (
    MemoryEntry,
    MemoryScope,
    apply_default_ttl,
    create_memory,
)
from agdd.storage.memory_store import SQLiteMemoryStore


class TestMemoryEntry:
    """Test MemoryEntry model."""

    def test_create_session_memory(self) -> None:
        """Test creating a SESSION scoped memory entry."""
        entry = MemoryEntry(
            scope=MemoryScope.SESSION,
            agent_slug="test-agent",
            run_id="run-123",
            key="test_key",
            value={"data": "test"},
        )

        assert entry.scope == MemoryScope.SESSION
        assert entry.agent_slug == "test-agent"
        assert entry.run_id == "run-123"
        assert entry.key == "test_key"
        assert entry.value == {"data": "test"}
        assert entry.memory_id is not None
        assert isinstance(entry.created_at, datetime)
        assert isinstance(entry.updated_at, datetime)

    def test_session_scope_requires_run_id(self) -> None:
        """Test that SESSION scope requires a run_id."""
        with pytest.raises(ValueError, match="run_id is required"):
            MemoryEntry(
                scope=MemoryScope.SESSION,
                agent_slug="test-agent",
                run_id=None,
                key="test_key",
                value={"data": "test"},
            )

    def test_long_term_scope_no_run_id(self) -> None:
        """Test that LONG_TERM scope does not require run_id."""
        entry = MemoryEntry(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="test_key",
            value={"data": "test"},
        )

        assert entry.scope == MemoryScope.LONG_TERM
        assert entry.run_id is None

    def test_pii_tags_validation(self) -> None:
        """Test PII tags validation."""
        entry = MemoryEntry(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="user_data",
            value={"email": "user@example.com"},
            pii_tags=["email"],
        )

        assert entry.pii_tags == ["email"]

    def test_invalid_pii_tag(self) -> None:
        """Test that invalid PII tags are rejected."""
        with pytest.raises(ValueError, match="Unknown PII tag"):
            MemoryEntry(
                scope=MemoryScope.LONG_TERM,
                agent_slug="test-agent",
                key="test_key",
                value={"data": "test"},
                pii_tags=["invalid_tag"],
            )

    def test_ttl_expiration(self) -> None:
        """Test TTL expiration checking."""
        entry = MemoryEntry(
            scope=MemoryScope.SESSION,
            agent_slug="test-agent",
            run_id="run-123",
            key="test_key",
            value={"data": "test"},
        )

        # Not expired initially
        assert not entry.is_expired()

        # Set TTL to 1 second in the past
        entry.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        assert entry.is_expired()

        # Set TTL to 1 hour in the future
        entry.expires_at = datetime.now(UTC) + timedelta(hours=1)
        assert not entry.is_expired()

    def test_set_ttl(self) -> None:
        """Test setting TTL."""
        entry = MemoryEntry(
            scope=MemoryScope.SESSION,
            agent_slug="test-agent",
            run_id="run-123",
            key="test_key",
            value={"data": "test"},
        )

        entry.set_ttl(3600)  # 1 hour
        assert entry.expires_at is not None
        assert entry.expires_at > datetime.now(UTC)
        assert entry.expires_at <= datetime.now(UTC) + timedelta(seconds=3601)


class TestMemoryUtilities:
    """Test memory utility functions."""

    def test_create_memory(self) -> None:
        """Test create_memory helper."""
        entry = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="test_key",
            value={"data": "test"},
            ttl_seconds=3600,
            pii_tags=["email"],
            tags=["important"],
            metadata={"source": "test"},
        )

        assert entry.scope == MemoryScope.LONG_TERM
        assert entry.agent_slug == "test-agent"
        assert entry.key == "test_key"
        assert entry.value == {"data": "test"}
        assert entry.expires_at is not None
        assert entry.pii_tags == ["email"]
        assert entry.tags == ["important"]
        assert entry.metadata == {"source": "test"}

    def test_apply_default_ttl(self) -> None:
        """Test default TTL for different scopes."""
        session_ttl = apply_default_ttl(MemoryScope.SESSION)
        long_term_ttl = apply_default_ttl(MemoryScope.LONG_TERM)
        org_ttl = apply_default_ttl(MemoryScope.ORG)

        assert session_ttl == 3600  # 1 hour
        assert long_term_ttl == 30 * 24 * 3600  # 30 days
        assert org_ttl == 90 * 24 * 3600  # 90 days


class TestSQLiteMemoryStore:
    """Test SQLite memory storage backend."""

    @pytest.fixture
    async def store(self) -> AsyncGenerator[SQLiteMemoryStore, None]:
        """Create a temporary SQLite memory store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_memory.db"
            store = SQLiteMemoryStore(db_path=db_path, enable_fts=True)
            await store.initialize()
            yield store
            await store.close()

    async def test_create_and_get_memory(self, store: SQLiteMemoryStore) -> None:
        """Test creating and retrieving a memory entry."""
        entry = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="test_key",
            value={"data": "test"},
        )

        await store.create_memory(entry)
        retrieved = await store.get_memory(entry.memory_id)

        assert retrieved is not None
        assert retrieved.memory_id == entry.memory_id
        assert retrieved.scope == entry.scope
        assert retrieved.agent_slug == entry.agent_slug
        assert retrieved.key == entry.key
        assert retrieved.value == entry.value

    async def test_create_duplicate_memory_fails(self, store: SQLiteMemoryStore) -> None:
        """Test that creating a memory with duplicate ID fails."""
        entry = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="test_key",
            value={"data": "test"},
        )

        await store.create_memory(entry)

        with pytest.raises(ValueError, match="already exists"):
            await store.create_memory(entry)

    async def test_update_memory(self, store: SQLiteMemoryStore) -> None:
        """Test updating a memory entry."""
        entry = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="test_key",
            value={"data": "test"},
        )

        await store.create_memory(entry)

        # Update the entry
        entry.value = {"data": "updated"}
        await store.update_memory(entry)

        retrieved = await store.get_memory(entry.memory_id)
        assert retrieved is not None
        assert retrieved.value == {"data": "updated"}

    async def test_delete_memory(self, store: SQLiteMemoryStore) -> None:
        """Test deleting a memory entry."""
        entry = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="test_key",
            value={"data": "test"},
        )

        await store.create_memory(entry)
        assert await store.delete_memory(entry.memory_id)

        retrieved = await store.get_memory(entry.memory_id)
        assert retrieved is None

    async def test_delete_nonexistent_memory(self, store: SQLiteMemoryStore) -> None:
        """Test deleting a non-existent memory returns False."""
        result = await store.delete_memory("nonexistent-id")
        assert result is False

    async def test_list_memories_by_scope(self, store: SQLiteMemoryStore) -> None:
        """Test listing memories by scope."""
        # Create memories with different scopes
        session_entry = create_memory(
            scope=MemoryScope.SESSION,
            agent_slug="test-agent",
            run_id="run-123",
            key="session_key",
            value={"data": "session"},
        )
        long_term_entry = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="long_term_key",
            value={"data": "long_term"},
        )

        await store.create_memory(session_entry)
        await store.create_memory(long_term_entry)

        # List SESSION memories
        session_memories = await store.list_memories(scope=MemoryScope.SESSION)
        assert len(session_memories) == 1
        assert session_memories[0].scope == MemoryScope.SESSION

        # List LONG_TERM memories
        long_term_memories = await store.list_memories(scope=MemoryScope.LONG_TERM)
        assert len(long_term_memories) == 1
        assert long_term_memories[0].scope == MemoryScope.LONG_TERM

    async def test_list_memories_by_agent(self, store: SQLiteMemoryStore) -> None:
        """Test listing memories by agent slug."""
        entry1 = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="agent-1",
            key="key1",
            value={"data": "test1"},
        )
        entry2 = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="agent-2",
            key="key2",
            value={"data": "test2"},
        )

        await store.create_memory(entry1)
        await store.create_memory(entry2)

        memories = await store.list_memories(agent_slug="agent-1")
        assert len(memories) == 1
        assert memories[0].agent_slug == "agent-1"

    async def test_list_memories_by_tags(self, store: SQLiteMemoryStore) -> None:
        """Test listing memories by tags."""
        entry1 = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="key1",
            value={"data": "test1"},
            tags=["important", "urgent"],
        )
        entry2 = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="key2",
            value={"data": "test2"},
            tags=["important"],
        )

        await store.create_memory(entry1)
        await store.create_memory(entry2)

        # Filter by single tag
        memories = await store.list_memories(tags=["important"])
        assert len(memories) == 2

        # Filter by multiple tags (AND logic)
        memories = await store.list_memories(tags=["important", "urgent"])
        assert len(memories) == 1
        assert memories[0].memory_id == entry1.memory_id

    async def test_expired_memory_not_returned(self, store: SQLiteMemoryStore) -> None:
        """Test that expired memories are not returned."""
        entry = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="test_key",
            value={"data": "test"},
            ttl_seconds=1,  # 1 second TTL
        )

        await store.create_memory(entry)

        # Should be retrievable initially
        retrieved = await store.get_memory(entry.memory_id)
        assert retrieved is not None

        # Wait for expiration
        import asyncio

        await asyncio.sleep(1.5)

        # Should not be retrievable after expiration
        retrieved = await store.get_memory(entry.memory_id)
        assert retrieved is None

    async def test_expire_old_memories(self, store: SQLiteMemoryStore) -> None:
        """Test expiring old memories."""
        # Create an expired memory
        expired_entry = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="expired_key",
            value={"data": "expired"},
        )
        expired_entry.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        # Create a non-expired memory
        valid_entry = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="valid_key",
            value={"data": "valid"},
        )

        await store.create_memory(expired_entry)
        await store.create_memory(valid_entry)

        # Expire old memories
        count = await store.expire_old_memories()
        assert count == 1

        # Verify expired memory is gone
        assert await store.get_memory(expired_entry.memory_id) is None

        # Verify valid memory still exists
        assert await store.get_memory(valid_entry.memory_id) is not None

    async def test_search_memories(self, store: SQLiteMemoryStore) -> None:
        """Test full-text search."""
        entry1 = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="user_preferences",
            value={"theme": "dark", "language": "python"},
        )
        entry2 = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="task_context",
            value={"task": "implement feature", "priority": "high"},
        )

        await store.create_memory(entry1)
        await store.create_memory(entry2)

        # Search by key
        results = await store.search_memories("preferences")
        assert len(results) == 1
        assert results[0].key == "user_preferences"

        # Search by value content
        results = await store.search_memories("python")
        assert len(results) == 1
        assert results[0].key == "user_preferences"

    async def test_vacuum(self, store: SQLiteMemoryStore) -> None:
        """Test vacuum operation."""
        # Create old and new memories
        old_entry = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="old_key",
            value={"data": "old"},
        )
        old_entry.created_at = datetime.now(UTC) - timedelta(days=100)

        new_entry = create_memory(
            scope=MemoryScope.LONG_TERM,
            agent_slug="test-agent",
            key="new_key",
            value={"data": "new"},
        )

        await store.create_memory(old_entry)
        await store.create_memory(new_entry)

        # Vacuum with dry run
        report = await store.vacuum(older_than_days=90, dry_run=True)
        assert report["would_delete_count"] == 1
        assert report["deleted_count"] == 0

        # Vacuum for real
        report = await store.vacuum(older_than_days=90, dry_run=False)
        assert report["deleted_count"] == 1

        # Verify old memory is gone
        assert await store.get_memory(old_entry.memory_id) is None

        # Verify new memory still exists
        assert await store.get_memory(new_entry.memory_id) is not None
