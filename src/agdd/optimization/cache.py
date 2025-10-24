"""Semantic cache with vector search support for AGDD framework.

This module provides efficient semantic caching using vector similarity search.
It supports multiple backends (FAISS and Redis Vector Index) and eliminates
O(N) linear scans through top-K similarity search.

Example:
    >>> from agdd.optimization.cache import create_cache, CacheConfig
    >>> config = CacheConfig(backend="faiss", dimension=768)
    >>> cache = create_cache(config)
    >>> import numpy as np
    >>> embedding = np.random.rand(768).astype(np.float32)
    >>> cache.set("key1", embedding, {"result": "cached value"})
    >>> matches = cache.search(embedding, k=5, threshold=0.8)
    >>> if matches:
    >>>     print(f"Found {len(matches)} similar entries")
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

import numpy as np
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class CacheBackend(str, Enum):
    """Available cache backend types."""

    FAISS = "faiss"
    REDIS = "redis"


@dataclass(frozen=True)
class CacheEntry:
    """Cache entry with metadata."""

    key: str
    embedding: np.ndarray[Any, np.dtype[np.float32]]
    value: dict[str, Any]
    distance: float = 0.0


class CacheConfig(BaseSettings):
    """Configuration for semantic cache.

    Attributes:
        backend: Cache backend type (faiss or redis)
        dimension: Embedding dimension (default: 768 for many models)
        redis_url: Redis connection URL (required for redis backend)
        redis_index_name: Redis index name (default: "agdd_cache")
        faiss_index_type: FAISS index type - "Flat" (exact) or "IVFFlat" (approximate)
        faiss_nlist: Number of clusters for IVFFlat index (default: 100)
    """

    model_config = SettingsConfigDict(
        env_prefix="AGDD_CACHE_",
        env_file=".env",
        extra="ignore",
    )

    backend: CacheBackend = Field(
        default=CacheBackend.FAISS,
        description="Cache backend type",
    )
    dimension: int = Field(
        default=768,
        gt=0,
        description="Embedding dimension",
    )
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL",
    )
    redis_index_name: str = Field(
        default="agdd_cache",
        description="Redis vector index name",
    )
    faiss_index_type: str = Field(
        default="Flat",
        description="FAISS index type: 'Flat' (exact search) or 'IVFFlat' (approximate)",
    )
    faiss_nlist: int = Field(
        default=100,
        gt=0,
        description="Number of IVF clusters",
    )


class SemanticCache(Protocol):
    """Protocol for semantic cache implementations."""

    @abstractmethod
    def set(
        self,
        key: str,
        embedding: np.ndarray[Any, np.dtype[np.float32]],
        value: dict[str, Any],
    ) -> None:
        """Store an entry in the cache.

        Args:
            key: Unique identifier for the entry
            embedding: Vector embedding (must be normalized)
            value: Associated metadata/value
        """
        ...

    @abstractmethod
    def search(
        self,
        query_embedding: np.ndarray[Any, np.dtype[np.float32]],
        k: int = 5,
        threshold: float = 0.9,
    ) -> list[CacheEntry]:
        """Search for similar entries using top-K similarity search.

        Args:
            query_embedding: Query vector (must be normalized)
            k: Number of top results to return
            threshold: Minimum similarity threshold (0.0-1.0)

        Returns:
            List of matching cache entries sorted by similarity
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear all entries from the cache."""
        ...

    @abstractmethod
    def size(self) -> int:
        """Get the number of entries in the cache."""
        ...


class FAISSCache(SemanticCache):
    """FAISS-based semantic cache implementation.

    Uses FAISS library for efficient approximate nearest neighbor search.
    Supports multiple index types for different scale/performance tradeoffs.
    """

    def __init__(self, config: CacheConfig) -> None:
        """Initialize FAISS cache.

        Args:
            config: Cache configuration
        """
        try:
            import faiss  # type: ignore[import-untyped]
        except ImportError as e:
            msg = (
                "FAISS backend requires faiss-cpu or faiss-gpu. "
                "Install with: pip install 'agdd[faiss]'"
            )
            raise ImportError(msg) from e

        self.config = config
        self.dimension = config.dimension
        self._metadata: dict[
            int, tuple[str, dict[str, Any], np.ndarray[Any, np.dtype[np.float32]]] | None
        ] = {}
        self._key_to_id: dict[str, int] = {}  # Track key uniqueness
        self._next_id = 0

        # Buffer for IVFFlat training
        self._training_buffer: list[tuple[int, np.ndarray[Any, np.dtype[np.float32]]]] = []
        self._trained = False

        # Create FAISS index based on configuration
        # Note: Only Flat and IVFFlat are supported for inner product (cosine similarity)
        # HNSW only supports L2 distance natively
        # Use IndexIDMap2 for removable vectors (prevents memory leaks on key updates)
        if config.faiss_index_type == "Flat":
            base_index: Any = faiss.IndexFlatIP(self.dimension)
            self.index = faiss.IndexIDMap2(base_index)
            self._trained = True  # Flat doesn't need training
        elif config.faiss_index_type == "IVFFlat":
            quantizer = faiss.IndexFlatIP(self.dimension)
            base_index = faiss.IndexIVFFlat(
                quantizer,
                self.dimension,
                config.faiss_nlist,
                faiss.METRIC_INNER_PRODUCT,
            )
            self.index = base_index  # Will wrap with IndexIDMap2 after training
        else:
            msg = (
                f"Unsupported FAISS index type: {config.faiss_index_type}. "
                f"Supported types: 'Flat' (exact), 'IVFFlat' (approximate)"
            )
            raise ValueError(msg)

        logger.info(
            "Initialized FAISS cache with %s index (dimension=%d)",
            config.faiss_index_type,
            self.dimension,
        )

    def _ensure_trained(self) -> None:
        """Ensure IVF index is trained if needed."""
        import faiss

        if self.config.faiss_index_type != "IVFFlat":
            return

        if not self._trained and len(self._training_buffer) >= self.config.faiss_nlist:
            # Extract embeddings and IDs from buffer, filtering out logically deleted entries
            ids_to_add = []
            embeddings_to_add = []
            for idx, embedding in self._training_buffer:
                # Only add if not logically deleted
                if self._metadata.get(idx) is not None:
                    ids_to_add.append(idx)
                    embeddings_to_add.append(embedding)

            # Only train if we have enough active embeddings (FAISS requires >= nlist)
            if len(embeddings_to_add) >= self.config.faiss_nlist:
                # Train the index with active embeddings
                train_data = np.array(embeddings_to_add, dtype=np.float32)
                self.index.train(train_data)

                # Wrap with IndexIDMap2 for removable vectors
                self.index = faiss.IndexIDMap2(self.index)

                # Add all active buffered embeddings with their IDs
                self.index.add_with_ids(
                    train_data,
                    np.array(ids_to_add, dtype=np.int64),
                )

                self._trained = True
                logger.info("Trained IVF index with %d vectors", len(embeddings_to_add))

                # Clear the buffer only after successful training
                self._training_buffer.clear()
            # else: keep buffering until we have enough active entries

    def set(
        self,
        key: str,
        embedding: np.ndarray[Any, np.dtype[np.float32]],
        value: dict[str, Any],
    ) -> None:
        """Store an entry in the cache.

        If the key already exists, the old entry is logically deleted
        and physically removed from the FAISS index to prevent memory leaks.
        """
        if embedding.shape[0] != self.dimension:
            msg = f"Embedding dimension {embedding.shape[0]} != {self.dimension}"
            raise ValueError(msg)

        # Normalize embedding for cosine similarity
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        # Check if key already exists and remove old entry
        if key in self._key_to_id:
            old_id = self._key_to_id[key]
            self._metadata[old_id] = None  # Logical deletion

            # Physical deletion from FAISS index (if trained)
            if self._trained:
                self.index.remove_ids(np.array([old_id], dtype=np.int64))

            logger.debug("Replacing existing cache entry for key: %s", key)

        # Store metadata with embedding
        current_id = self._next_id
        self._metadata[current_id] = (key, value, embedding.copy())
        self._key_to_id[key] = current_id
        self._next_id += 1

        # For IVFFlat, buffer embeddings until we have enough to train
        if self.config.faiss_index_type == "IVFFlat" and not self._trained:
            self._training_buffer.append((current_id, embedding.copy()))
            self._ensure_trained()
        else:
            # Add to FAISS index directly with ID
            self.index.add_with_ids(
                embedding.reshape(1, -1),
                np.array([current_id], dtype=np.int64),
            )

    def search(
        self,
        query_embedding: np.ndarray[Any, np.dtype[np.float32]],
        k: int = 5,
        threshold: float = 0.9,
    ) -> list[CacheEntry]:
        """Search for similar entries using FAISS."""
        if query_embedding.shape[0] != self.dimension:
            msg = f"Query dimension {query_embedding.shape[0]} != {self.dimension}"
            raise ValueError(msg)

        if self._next_id == 0:
            return []

        # Normalize query
        norm = np.linalg.norm(query_embedding)
        if norm > 0:
            query_embedding = query_embedding / norm

        results: list[CacheEntry] = []

        # Search buffered embeddings (for untrained IVFFlat)
        if self._training_buffer:
            for idx, emb in self._training_buffer:
                similarity = float(np.dot(query_embedding, emb))
                if similarity >= threshold:
                    entry = self._metadata.get(idx)
                    if entry is not None:  # Skip logically deleted entries
                        key, value, stored_emb = entry
                        results.append(
                            CacheEntry(
                                key=key,
                                embedding=stored_emb,
                                value=value,
                                distance=1.0 - similarity,
                            )
                        )

        # Search FAISS index if trained
        if self._trained and self.index.ntotal > 0:
            k_actual = min(k, self.index.ntotal)
            distances, indices = self.index.search(query_embedding.reshape(1, -1), k_actual)

            for dist, idx in zip(distances[0], indices[0]):
                # FAISS inner product returns similarity (higher is better)
                similarity = float(dist)
                if similarity >= threshold:
                    entry = self._metadata.get(int(idx))
                    if entry is not None:  # Skip logically deleted entries
                        key, value, emb = entry
                        results.append(
                            CacheEntry(
                                key=key,
                                embedding=emb,
                                value=value,
                                distance=1.0 - similarity,  # Convert to distance
                            )
                        )

        # Sort by distance and limit to k results
        results.sort(key=lambda x: x.distance)
        return results[:k]

    def clear(self) -> None:
        """Clear all entries from the cache."""
        self._metadata.clear()
        self._key_to_id.clear()
        self._next_id = 0
        self._training_buffer.clear()

        if self.config.faiss_index_type == "IVFFlat":
            # Recreate untrained IVFFlat index (after training, index is wrapped with IndexIDMap2,
            # which doesn't have train() method, so we need to recreate the base index)
            import faiss

            quantizer = faiss.IndexFlatIP(self.dimension)
            self.index = faiss.IndexIVFFlat(
                quantizer,
                self.dimension,
                self.config.faiss_nlist,
                faiss.METRIC_INNER_PRODUCT,
            )
            self._trained = False
        else:
            # Flat index can be reset (already wrapped with IndexIDMap2, no training needed)
            self.index.reset()

    def size(self) -> int:
        """Get the number of unique entries in the cache.

        Returns the count of unique keys (excluding logically deleted entries).
        """
        return len(self._key_to_id)


class RedisVectorCache(SemanticCache):
    """Redis Vector Index-based semantic cache implementation.

    Uses Redis Stack with RediSearch vector similarity for production-grade
    distributed caching with persistence.
    """

    def __init__(self, config: CacheConfig) -> None:
        """Initialize Redis vector cache.

        Args:
            config: Cache configuration
        """
        try:
            from redis import Redis
            from redis.commands.search.field import TextField, VectorField
            from redis.commands.search.indexDefinition import (  # type: ignore[import-not-found]
                IndexDefinition,
                IndexType,
            )
        except ImportError as e:
            msg = (
                "Redis backend requires redis and redis-py with search support. "
                "Install with: pip install 'agdd[redis]'"
            )
            raise ImportError(msg) from e

        self.config = config
        self.dimension = config.dimension
        self.index_name = config.redis_index_name

        # Connect to Redis
        self.redis: Any = Redis.from_url(config.redis_url, decode_responses=False)

        # Create vector index if it doesn't exist
        try:
            self.redis.ft(self.index_name).info()  # type: ignore[no-untyped-call]
            logger.info("Using existing Redis index: %s", self.index_name)
        except Exception:
            # Index doesn't exist, create it
            schema = (
                TextField("key"),
                VectorField(
                    "embedding",
                    "HNSW",
                    {
                        "TYPE": "FLOAT32",
                        "DIM": self.dimension,
                        "DISTANCE_METRIC": "COSINE",
                    },
                ),
                TextField("value"),
            )
            definition = IndexDefinition(
                prefix=[f"{self.index_name}:"],
                index_type=IndexType.HASH,
            )
            self.redis.ft(self.index_name).create_index(
                schema,
                definition=definition,
            )
            logger.info("Created Redis vector index: %s", self.index_name)

    def set(
        self,
        key: str,
        embedding: np.ndarray[Any, np.dtype[np.float32]],
        value: dict[str, Any],
    ) -> None:
        """Store an entry in the cache."""
        import json

        if embedding.shape[0] != self.dimension:
            msg = f"Embedding dimension {embedding.shape[0]} != {self.dimension}"
            raise ValueError(msg)

        # Normalize embedding for cosine similarity
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        # Store in Redis
        redis_key = f"{self.index_name}:{key}"
        self.redis.hset(
            redis_key,
            mapping={
                "key": key,
                "embedding": embedding.tobytes(),
                "value": json.dumps(value),
            },
        )

    def search(
        self,
        query_embedding: np.ndarray[Any, np.dtype[np.float32]],
        k: int = 5,
        threshold: float = 0.9,
    ) -> list[CacheEntry]:
        """Search for similar entries using Redis vector search."""
        import json

        from redis.commands.search.query import Query

        if query_embedding.shape[0] != self.dimension:
            msg = f"Query dimension {query_embedding.shape[0]} != {self.dimension}"
            raise ValueError(msg)

        # Normalize query
        norm = np.linalg.norm(query_embedding)
        if norm > 0:
            query_embedding = query_embedding / norm

        # Convert threshold to range (Redis uses distance, not similarity)
        # For cosine distance: distance = 1 - similarity
        max_distance = 1.0 - threshold

        # Search Redis
        query = (
            Query(f"*=>[KNN {k} @embedding $vec AS distance]")
            .sort_by("distance")
            .return_fields("key", "embedding", "value", "distance")
            .paging(0, k)
            .dialect(2)
        )

        query_params = {"vec": query_embedding.tobytes()}

        results_raw = self.redis.ft(self.index_name).search(query, query_params)

        # Parse results
        results: list[CacheEntry] = []
        for doc in results_raw.docs:
            distance = float(doc.distance)
            if distance <= max_distance:
                key = doc.key.decode() if isinstance(doc.key, bytes) else doc.key
                value_str = doc.value.decode() if isinstance(doc.value, bytes) else doc.value

                # Handle embedding field: redis-py returns vector fields as memoryview
                if isinstance(doc.embedding, bytes):
                    embedding_bytes = doc.embedding
                elif isinstance(doc.embedding, memoryview):
                    embedding_bytes = bytes(doc.embedding)
                else:
                    # Fallback for string or other types
                    embedding_bytes = doc.embedding.encode()

                results.append(
                    CacheEntry(
                        key=key,
                        embedding=np.frombuffer(embedding_bytes, dtype=np.float32),
                        value=json.loads(value_str),
                        distance=distance,
                    )
                )

        return results

    def clear(self) -> None:
        """Clear all entries from the cache."""
        # Delete all keys with the index prefix
        pattern = f"{self.index_name}:*"
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(cursor, match=pattern, count=100)
            if keys:
                self.redis.delete(*keys)
            if cursor == 0:
                break

    def size(self) -> int:
        """Get the number of entries in the cache."""
        try:
            info = self.redis.ft(self.index_name).info()
            return int(info.get("num_docs", 0))
        except Exception:
            return 0


def create_cache(config: CacheConfig | None = None) -> SemanticCache:
    """Factory function to create a semantic cache instance.

    Args:
        config: Cache configuration. If None, uses default settings.

    Returns:
        Configured semantic cache instance

    Example:
        >>> config = CacheConfig(backend="faiss", dimension=768)
        >>> cache = create_cache(config)
    """
    if config is None:
        config = CacheConfig()

    if config.backend == CacheBackend.FAISS:
        return FAISSCache(config)
    elif config.backend == CacheBackend.REDIS:
        return RedisVectorCache(config)
    else:
        msg = f"Unknown backend: {config.backend}"
        raise ValueError(msg)
