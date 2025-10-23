"""
Storage abstraction layer for AGDD observability data.

Provides capability-based storage backends that can range from simple
file-based storage to sophisticated database systems with full-text search,
time-series optimization, and lifecycle management.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol


@dataclass
class StorageCapabilities:
    """
    Capabilities supported by a storage backend.

    This allows runtime feature detection and graceful degradation
    when switching between storage backends.
    """

    append_event: bool = True  # Can append events
    get_run: bool = True  # Can retrieve run metadata
    list_runs: bool = True  # Can list runs with filters
    query_metrics: bool = False  # Can query aggregated metrics
    search_text: bool = False  # Full-text search support
    vector_search: bool = False  # Vector similarity search
    archive_artifacts: bool = False  # Can archive to object storage
    lifecycle_policy: bool = False  # Automatic data retention/archival
    streaming: bool = False  # Can stream events in real-time


class StorageBackend(Protocol):
    """
    Protocol for pluggable storage backends.

    Implementations can range from SQLite (dev) to PostgreSQL/TimescaleDB (prod)
    to ClickHouse (analytics) while maintaining a consistent interface.
    """

    @property
    @abstractmethod
    def capabilities(self) -> StorageCapabilities:
        """Return capabilities supported by this backend"""
        ...

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize storage (create tables, indexes, etc.)"""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close connections and cleanup resources"""
        ...

    @abstractmethod
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
        """
        Append an event to storage.

        Args:
            run_id: Unique run identifier
            agent_slug: Agent slug (MAG/SAG identifier)
            event_type: Event type (e.g., 'log', 'mcp.call', 'metric', 'artifact')
            timestamp: Event timestamp
            level: Log level (info, warn, error, etc.)
            message: Human-readable message
            payload: Flexible JSON payload with agent-specific data
            span_id: OpenTelemetry span ID (optional)
            parent_span_id: Parent span ID for hierarchical tracing
            contract_id: JSON Schema contract identifier
            contract_version: Contract version
        """
        ...

    @abstractmethod
    async def create_run(
        self,
        run_id: str,
        agent_slug: str,
        parent_run_id: Optional[str] = None,
        started_at: Optional[datetime] = None,
        status: str = "running",
        tags: Optional[List[str]] = None,
    ) -> None:
        """
        Create a new run record.

        Args:
            run_id: Unique run identifier
            agent_slug: Agent slug
            parent_run_id: Parent run ID for sub-agent delegations
            started_at: Start timestamp (defaults to now)
            status: Initial status (running, succeeded, failed, canceled)
            tags: Optional tags for categorization
        """
        ...

    @abstractmethod
    async def update_run(
        self,
        run_id: str,
        status: Optional[str] = None,
        ended_at: Optional[datetime] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Update run metadata.

        Args:
            run_id: Run identifier
            status: Final status
            ended_at: End timestamp
            metrics: Aggregated metrics (token counts, costs, latency, etc.)
        """
        ...

    @abstractmethod
    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Get run metadata.

        Returns:
            Run metadata dict or None if not found
        """
        ...

    @abstractmethod
    async def list_runs(
        self,
        agent_slug: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List runs with optional filters.

        Args:
            agent_slug: Filter by agent slug
            status: Filter by status
            since: Filter by start time (inclusive)
            until: Filter by start time (exclusive)
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of run metadata dicts
        """
        ...

    @abstractmethod
    async def get_events(
        self,
        run_id: str,
        event_type: Optional[str] = None,
        level: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream events for a run.

        Args:
            run_id: Run identifier
            event_type: Filter by event type
            level: Filter by log level
            limit: Maximum number of events to return

        Yields:
            Event dicts in chronological order
        """
        ...

    async def search_text(
        self,
        query: str,
        agent_slug: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Full-text search across event messages (if supported).

        Args:
            query: Search query
            agent_slug: Filter by agent
            since: Filter by timestamp
            limit: Maximum results

        Returns:
            Matching events

        Raises:
            NotImplementedError: If full-text search not supported
        """
        raise NotImplementedError("Full-text search not supported by this backend")

    async def query_metrics(
        self,
        metric_name: str,
        agent_slug: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        aggregation: str = "avg",
    ) -> List[Dict[str, Any]]:
        """
        Query aggregated metrics (if supported).

        Args:
            metric_name: Metric to query (e.g., 'duration_ms', 'token_count')
            agent_slug: Filter by agent
            since: Start time
            until: End time
            aggregation: Aggregation function (avg, sum, count, min, max)

        Returns:
            Time-bucketed metric values

        Raises:
            NotImplementedError: If metric queries not supported
        """
        raise NotImplementedError("Metric queries not supported by this backend")

    async def vacuum(
        self,
        hot_days: int = 7,
        max_disk_mb: Optional[int] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Clean up old data based on retention policy.

        Args:
            hot_days: Keep data newer than this many days
            max_disk_mb: Target maximum disk usage in MB
            dry_run: If True, only report what would be deleted

        Returns:
            Report of deleted/archived data

        Raises:
            NotImplementedError: If vacuum not supported
        """
        raise NotImplementedError("Vacuum not supported by this backend")

    async def archive(
        self,
        destination: str,
        since_days: int = 7,
        format: str = "parquet",
    ) -> Dict[str, Any]:
        """
        Archive old data to external storage (S3, MinIO, etc.).

        Args:
            destination: Archive destination URI (e.g., s3://bucket/prefix)
            since_days: Archive data older than this many days
            format: Archive format (parquet, ndjson)

        Returns:
            Archive report

        Raises:
            NotImplementedError: If archival not supported
        """
        raise NotImplementedError("Archival not supported by this backend")
