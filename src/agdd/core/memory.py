"""
Memory IR (Intermediate Representation) layer for AGDD.

Provides structured memory storage with scoping, TTL, PII tagging,
and retention policies for agent context persistence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class MemoryScope(str, Enum):
    """
    Memory scope defines the lifetime and visibility of memory entries.

    - SESSION: Memory scoped to a single agent run (ephemeral)
    - LONG_TERM: Memory persisted across runs for the same agent
    - ORG: Memory shared across all agents in an organization
    """

    SESSION = "session"
    LONG_TERM = "long_term"
    ORG = "org"


class MemoryEntry(BaseModel):
    """
    Memory entry representing a single piece of stored context.

    Includes metadata for governance (TTL, PII tags), retrieval (embeddings),
    and observability (provenance tracking).
    """

    # Core identification
    memory_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique memory identifier",
    )
    scope: MemoryScope = Field(description="Memory scope (session, long_term, org)")
    agent_slug: str = Field(description="Agent that created this memory")
    run_id: Optional[str] = Field(
        default=None,
        description="Run ID if scope is SESSION",
    )

    # Content
    key: str = Field(
        description="Human-readable key for retrieval (e.g., 'user_preferences', 'task_context')"
    )
    value: Dict[str, Any] = Field(
        description="Flexible JSON value containing the memory data"
    )

    # Lifecycle management
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: Optional[datetime] = Field(
        default=None,
        description="TTL expiration timestamp (None = no expiration)",
    )

    # Governance & compliance
    pii_tags: List[str] = Field(
        default_factory=list,
        description="PII tags for compliance (e.g., ['email', 'phone', 'ssn'])",
    )
    retention_policy: Optional[str] = Field(
        default=None,
        description="Named retention policy to apply (references retention_policy.yaml)",
    )

    # Retrieval optimization
    embedding: Optional[List[float]] = Field(
        default=None,
        description="Vector embedding for semantic search (optional)",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Tags for filtering and categorization",
    )

    # Provenance
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (source, version, etc.)",
    )

    @field_validator("run_id")
    @classmethod
    def validate_session_run_id(cls, v: Optional[str], info: Any) -> Optional[str]:
        """Validate that SESSION scope entries have a run_id."""
        scope = info.data.get("scope")
        if scope == MemoryScope.SESSION and not v:
            raise ValueError("run_id is required for SESSION scope memories")
        return v

    @field_validator("pii_tags")
    @classmethod
    def validate_pii_tags(cls, v: List[str]) -> List[str]:
        """Validate PII tags against known types."""
        known_pii_tags = {
            "email",
            "phone",
            "ssn",
            "name",
            "address",
            "credit_card",
            "ip_address",
            "biometric",
            "health",
            "financial",
        }
        for tag in v:
            if tag not in known_pii_tags:
                raise ValueError(
                    f"Unknown PII tag '{tag}'. Known tags: {', '.join(sorted(known_pii_tags))}"
                )
        return v

    def is_expired(self) -> bool:
        """Check if this memory entry has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) >= self.expires_at

    def set_ttl(self, ttl_seconds: int) -> None:
        """Set TTL for this memory entry."""
        self.expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        self.updated_at = datetime.now(UTC)


def create_memory(
    scope: MemoryScope,
    agent_slug: str,
    key: str,
    value: Dict[str, Any],
    run_id: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
    pii_tags: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    retention_policy: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> MemoryEntry:
    """
    Create a new memory entry with proper defaults.

    Args:
        scope: Memory scope (SESSION, LONG_TERM, ORG)
        agent_slug: Agent creating the memory
        key: Memory key for retrieval
        value: Memory value (flexible JSON)
        run_id: Run ID (required for SESSION scope)
        ttl_seconds: Optional TTL in seconds
        pii_tags: Optional PII tags for compliance
        tags: Optional tags for filtering
        retention_policy: Optional named retention policy
        metadata: Optional additional metadata

    Returns:
        MemoryEntry instance

    Raises:
        ValueError: If validation fails
    """
    entry = MemoryEntry(
        scope=scope,
        agent_slug=agent_slug,
        key=key,
        value=value,
        run_id=run_id,
        pii_tags=pii_tags or [],
        tags=tags or [],
        retention_policy=retention_policy,
        metadata=metadata or {},
    )

    if ttl_seconds is not None:
        entry.set_ttl(ttl_seconds)

    return entry


def apply_default_ttl(scope: MemoryScope) -> int:
    """
    Get default TTL for a memory scope.

    Args:
        scope: Memory scope

    Returns:
        Default TTL in seconds
    """
    ttl_map = {
        MemoryScope.SESSION: 3600,  # 1 hour
        MemoryScope.LONG_TERM: 30 * 24 * 3600,  # 30 days
        MemoryScope.ORG: 90 * 24 * 3600,  # 90 days
    }
    return ttl_map.get(scope, 24 * 3600)  # Default: 24 hours
