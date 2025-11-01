"""
MAGSAG Storage layer for observability data.

Provides pluggable storage backends with capability-based feature detection.
Default backend is SQLite for development; PostgreSQL/TimescaleDB recommended
for production.
"""

from magsag.storage.base import StorageBackend, StorageCapabilities
from magsag.storage.backends import PostgresStorageBackend, SQLiteStorageBackend
from magsag.storage.factory import (
    close_storage_backend,
    create_storage_backend,
    get_storage_backend,
)
from magsag.storage.models import (
    ArtifactEvent,
    DelegationEvent,
    Event,
    MCPCallEvent,
    MetricEvent,
    Run,
)

__all__ = [
    "StorageBackend",
    "StorageCapabilities",
    "SQLiteStorageBackend",
    "PostgresStorageBackend",
    "Event",
    "Run",
    "MCPCallEvent",
    "DelegationEvent",
    "MetricEvent",
    "ArtifactEvent",
    "create_storage_backend",
    "get_storage_backend",
    "close_storage_backend",
]
