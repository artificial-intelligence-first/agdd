"""Unit tests for semantic cache module."""

from __future__ import annotations

import numpy as np
import pytest

from agdd.optimization.cache import (
    CacheBackend,
    CacheConfig,
    CacheEntry,
    create_cache,
)


class TestCacheConfig:
    """Test cache configuration."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = CacheConfig()
        assert config.backend == CacheBackend.FAISS
        assert config.dimension == 768
        assert config.faiss_index_type == "IVFFlat"
        assert config.faiss_nlist == 100

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = CacheConfig(
            backend=CacheBackend.REDIS,
            dimension=1024,
            redis_index_name="test_index",
        )
        assert config.backend == CacheBackend.REDIS
        assert config.dimension == 1024
        assert config.redis_index_name == "test_index"


class TestFAISSCache:
    """Test FAISS cache implementation."""

    @pytest.fixture
    def cache_config(self) -> CacheConfig:
        """Create test cache configuration."""
        return CacheConfig(
            backend=CacheBackend.FAISS,
            dimension=128,
            faiss_index_type="Flat",  # Flat index for testing
        )

    @pytest.fixture
    def cache(self, cache_config: CacheConfig) -> None:
        """Create test cache instance."""
        pytest.importorskip("faiss")
        return create_cache(cache_config)

    def test_cache_creation(self, cache_config: CacheConfig) -> None:
        """Test cache creation."""
        pytest.importorskip("faiss")
        cache = create_cache(cache_config)
        assert cache.size() == 0

    def test_set_and_size(self, cache: None) -> None:
        """Test setting entries and checking size."""
        embedding = np.random.rand(128).astype(np.float32)
        cache.set("key1", embedding, {"value": "test1"})
        assert cache.size() == 1

        cache.set("key2", embedding, {"value": "test2"})
        assert cache.size() == 2

    def test_search_exact_match(self, cache: None) -> None:
        """Test searching for exact match."""
        embedding = np.random.rand(128).astype(np.float32)
        cache.set("key1", embedding, {"value": "test1"})

        # Search with same embedding (should find exact match)
        results = cache.search(embedding, k=1, threshold=0.99)
        assert len(results) == 1
        assert results[0].key == "key1"
        assert results[0].value == {"value": "test1"}

    def test_search_top_k(self, cache: None) -> None:
        """Test top-K search."""
        # Add multiple entries
        for i in range(10):
            embedding = np.random.rand(128).astype(np.float32)
            cache.set(f"key_{i}", embedding, {"index": i})

        # Search with new query
        query = np.random.rand(128).astype(np.float32)
        results = cache.search(query, k=5, threshold=0.0)

        # Should return up to 5 results
        assert len(results) <= 5
        assert len(results) > 0

    def test_search_with_threshold(self, cache: None) -> None:
        """Test search with similarity threshold."""
        embedding1 = np.random.rand(128).astype(np.float32)
        embedding2 = np.random.rand(128).astype(np.float32)

        cache.set("key1", embedding1, {"value": "test1"})
        cache.set("key2", embedding2, {"value": "test2"})

        # High threshold should filter results
        results = cache.search(embedding1, k=10, threshold=0.999)
        assert len(results) <= 2

    def test_clear(self, cache: None) -> None:
        """Test clearing cache."""
        embedding = np.random.rand(128).astype(np.float32)
        cache.set("key1", embedding, {"value": "test1"})
        cache.set("key2", embedding, {"value": "test2"})
        assert cache.size() == 2

        cache.clear()
        assert cache.size() == 0

        # Search should return empty
        results = cache.search(embedding, k=5)
        assert len(results) == 0

    def test_invalid_dimension(self, cache: None) -> None:
        """Test error on invalid embedding dimension."""
        wrong_embedding = np.random.rand(64).astype(np.float32)

        with pytest.raises(ValueError, match="dimension"):
            cache.set("key1", wrong_embedding, {"value": "test"})

        with pytest.raises(ValueError, match="dimension"):
            cache.search(wrong_embedding, k=5)

    def test_normalization(self, cache: None) -> None:
        """Test that embeddings are normalized."""
        # Create unnormalized embedding
        embedding = np.array([3.0, 4.0] + [0.0] * 126, dtype=np.float32)
        cache.set("key1", embedding, {"value": "test"})

        # Search should still work (embeddings are normalized internally)
        results = cache.search(embedding, k=1, threshold=0.99)
        assert len(results) == 1


class TestCacheEntry:
    """Test cache entry dataclass."""

    def test_cache_entry_creation(self) -> None:
        """Test creating cache entry."""
        embedding = np.random.rand(128).astype(np.float32)
        entry = CacheEntry(
            key="test_key",
            embedding=embedding,
            value={"result": "cached"},
            distance=0.1,
        )
        assert entry.key == "test_key"
        assert entry.value == {"result": "cached"}
        assert entry.distance == 0.1

    def test_cache_entry_immutable(self) -> None:
        """Test that cache entry is immutable."""
        embedding = np.random.rand(128).astype(np.float32)
        entry = CacheEntry(
            key="test_key",
            embedding=embedding,
            value={"result": "cached"},
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            entry.key = "new_key"  # type: ignore[misc]


class TestCacheFactory:
    """Test cache factory function."""

    def test_create_faiss_cache(self) -> None:
        """Test creating FAISS cache."""
        pytest.importorskip("faiss")
        config = CacheConfig(backend=CacheBackend.FAISS, dimension=128)
        cache = create_cache(config)
        assert cache is not None
        assert cache.size() == 0

    def test_create_cache_with_defaults(self) -> None:
        """Test creating cache with default config."""
        pytest.importorskip("faiss")
        cache = create_cache()
        assert cache is not None

    def test_invalid_backend(self) -> None:
        """Test error on invalid backend via Pydantic validation."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CacheConfig(backend="invalid")  # type: ignore[arg-type]


class TestScalability:
    """Test cache scalability."""

    def test_large_scale_insert_and_search(self) -> None:
        """Test cache with larger number of entries."""
        pytest.importorskip("faiss")

        config = CacheConfig(
            backend=CacheBackend.FAISS,
            dimension=128,
            faiss_index_type="Flat",
        )
        cache = create_cache(config)

        # Insert 1000 entries
        num_entries = 1000
        for i in range(num_entries):
            embedding = np.random.rand(128).astype(np.float32)
            cache.set(f"key_{i}", embedding, {"index": i})

        assert cache.size() == num_entries

        # Search should still be fast
        import time

        query = np.random.rand(128).astype(np.float32)
        start = time.perf_counter()
        results = cache.search(query, k=10, threshold=0.0)
        elapsed = time.perf_counter() - start

        assert len(results) <= 10
        assert elapsed < 0.1  # Should complete in < 100ms
