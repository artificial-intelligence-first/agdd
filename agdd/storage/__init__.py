"""
AGDD Storage layer for observability data.

Provides pluggable storage backends with capability-based feature detection.
Default backend is SQLite for development; PostgreSQL/TimescaleDB recommended
for production.
"""

from agdd.storage.base import StorageBackend, StorageCapabilities
from agdd.storage.backends import SQLiteStorageBackend
from agdd.storage.factory import (
    close_storage_backend,
    create_storage_backend,
    get_storage_backend,
)
from agdd.storage.models import (
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
