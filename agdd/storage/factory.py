"""
Storage backend factory.

Provides a centralized way to create and configure storage backends
based on application settings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agdd.storage.backends.sqlite import SQLiteStorageBackend

if TYPE_CHECKING:
    from agdd.api.config import Settings
    from agdd.storage.base import StorageBackend


async def create_storage_backend(settings: Settings) -> StorageBackend:
    """
    Create and initialize a storage backend based on settings.

    Args:
        settings: Application settings

    Returns:
        Initialized storage backend

    Raises:
        ValueError: If backend type is unsupported
    """
    backend_type = settings.STORAGE_BACKEND.lower()

    if backend_type == "sqlite":
        backend = SQLiteStorageBackend(
            db_path=settings.STORAGE_DB_PATH,
            enable_fts=settings.STORAGE_ENABLE_FTS,
        )
    elif backend_type in ("postgres", "postgresql", "timescale", "timescaledb"):
        # Future: PostgreSQL/TimescaleDB backend
        raise NotImplementedError(
            f"Backend '{backend_type}' not yet implemented. "
            "Currently supported: sqlite"
        )
    else:
        raise ValueError(
            f"Unsupported storage backend: {backend_type}. "
            "Supported backends: sqlite, postgres, timescale"
        )

    # Initialize the backend
    await backend.initialize()

    return backend


# Global storage backend instance (singleton)
_storage_backend: StorageBackend | None = None


async def get_storage_backend(settings: Settings | None = None) -> StorageBackend:
    """
    Get or create the global storage backend instance.

    Args:
        settings: Application settings (optional, will use get_settings() if None)

    Returns:
        Storage backend instance
    """
    global _storage_backend

    if _storage_backend is None:
        if settings is None:
            from agdd.api.config import get_settings

            settings = get_settings()

        _storage_backend = await create_storage_backend(settings)

    return _storage_backend


async def close_storage_backend() -> None:
    """Close and cleanup the global storage backend."""
    global _storage_backend

    if _storage_backend is not None:
        await _storage_backend.close()
        _storage_backend = None
