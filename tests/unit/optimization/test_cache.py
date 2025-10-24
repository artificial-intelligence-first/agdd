"""Unit tests for semantic cache module."""

from __future__ import annotations

import pytest

# Skip all tests if numpy is not installed
np = pytest.importorskip("numpy")

from agdd.optimization.cache import (  # noqa: E402
    CacheBackend,
    CacheConfig,
    CacheEntry,
    SemanticCache,
    create_cache,
)


class TestCacheConfig:
    """Test cache configuration."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = CacheConfig()
        assert config.backend == CacheBackend.FAISS
        assert config.dimension == 768
        assert config.faiss_index_type == "Flat"
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

    def test_unsupported_index_type(self) -> None:
        """Test error on unsupported FAISS index type."""
        pytest.importorskip("faiss")

        config = CacheConfig(
            backend=CacheBackend.FAISS,
            dimension=128,
            faiss_index_type="HNSW",  # Not supported
        )
        with pytest.raises(ValueError, match="Unsupported FAISS index type"):
            create_cache(config)


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
    def cache(self, cache_config: CacheConfig) -> SemanticCache:
        """Create test cache instance."""
        pytest.importorskip("faiss")
        return create_cache(cache_config)

    def test_cache_creation(self, cache_config: CacheConfig) -> None:
        """Test cache creation."""
        pytest.importorskip("faiss")
        cache = create_cache(cache_config)
        assert cache.size() == 0

    def test_set_and_size(self, cache: SemanticCache) -> None:
        """Test setting entries and checking size."""
        embedding = np.random.rand(128).astype(np.float32)
        cache.set("key1", embedding, {"value": "test1"})
        assert cache.size() == 1

        cache.set("key2", embedding, {"value": "test2"})
        assert cache.size() == 2

    def test_search_exact_match(self, cache: SemanticCache) -> None:
        """Test searching for exact match."""
        embedding = np.random.rand(128).astype(np.float32)
        cache.set("key1", embedding, {"value": "test1"})

        # Search with same embedding (should find exact match)
        results = cache.search(embedding, k=1, threshold=0.99)
        assert len(results) == 1
        assert results[0].key == "key1"
        assert results[0].value == {"value": "test1"}

    def test_search_top_k(self, cache: SemanticCache) -> None:
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

    def test_search_with_threshold(self, cache: SemanticCache) -> None:
        """Test search with similarity threshold."""
        embedding1 = np.random.rand(128).astype(np.float32)
        embedding2 = np.random.rand(128).astype(np.float32)

        cache.set("key1", embedding1, {"value": "test1"})
        cache.set("key2", embedding2, {"value": "test2"})

        # High threshold should filter results
        results = cache.search(embedding1, k=10, threshold=0.999)
        assert len(results) <= 2

    def test_clear(self, cache: SemanticCache) -> None:
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

    def test_key_overwrite(self, cache: SemanticCache) -> None:
        """Test that setting the same key twice overwrites the old value."""
        embedding1 = np.random.rand(128).astype(np.float32)
        embedding2 = np.random.rand(128).astype(np.float32)

        # Set initial value
        cache.set("key1", embedding1, {"value": "original"})
        assert cache.size() == 1

        # Overwrite with new value
        cache.set("key1", embedding2, {"value": "updated"})
        assert cache.size() == 1  # Size should stay the same

        # Search should only return the new value
        results = cache.search(embedding2, k=10, threshold=0.99)
        assert len(results) == 1
        assert results[0].key == "key1"
        assert results[0].value == {"value": "updated"}

        # Old embedding should not be found
        results = cache.search(embedding1, k=10, threshold=0.99)
        # May or may not find it depending on similarity, but should have updated value
        for result in results:
            if result.key == "key1":
                assert result.value == {"value": "updated"}

    def test_multiple_key_overwrites(self, cache: SemanticCache) -> None:
        """Test multiple overwrites maintain correct size."""
        # Add multiple entries
        for i in range(5):
            embedding = np.random.rand(128).astype(np.float32)
            cache.set(f"key_{i}", embedding, {"index": i, "version": 1})

        assert cache.size() == 5

        # Overwrite some keys
        for i in range(3):
            embedding = np.random.rand(128).astype(np.float32)
            cache.set(f"key_{i}", embedding, {"index": i, "version": 2})

        # Size should still be 5 (no duplicates)
        assert cache.size() == 5

        # Overwrite the same key multiple times
        for version in range(3, 6):
            embedding = np.random.rand(128).astype(np.float32)
            cache.set("key_0", embedding, {"index": 0, "version": version})

        # Size should still be 5
        assert cache.size() == 5

    def test_no_memory_leak_on_key_replacement(self, cache: SemanticCache) -> None:
        """Test that replacing keys doesn't leak memory in FAISS index.

        This test verifies that when a key is updated, the old vector is physically
        removed from the FAISS index, not just logically deleted from metadata.
        """
        # Get access to the underlying FAISS cache to check index size
        from agdd.optimization.cache import FAISSCache

        assert isinstance(cache, FAISSCache), "This test requires FAISS cache"

        # Add initial entry
        embedding1 = np.random.rand(128).astype(np.float32)
        cache.set("key1", embedding1, {"value": "v1"})

        # Check initial state
        assert cache.size() == 1
        initial_ntotal = cache.index.ntotal
        assert initial_ntotal == 1, "FAISS index should have 1 vector"

        # Replace the same key 10 times
        for i in range(2, 12):
            embedding = np.random.rand(128).astype(np.float32)
            cache.set("key1", embedding, {"value": f"v{i}"})

            # Verify size stays at 1
            assert cache.size() == 1, f"Cache size should stay at 1 (iteration {i})"

            # Verify FAISS index size stays at 1 (no memory leak)
            assert cache.index.ntotal == 1, (
                f"FAISS index size should stay at 1, got {cache.index.ntotal} "
                f"after {i} updates (memory leak detected)"
            )

        # Verify only the latest value is searchable
        results = cache.search(embedding, k=10, threshold=0.99)
        assert len(results) == 1
        assert results[0].value == {"value": "v11"}

        # Add a different key
        embedding_new = np.random.rand(128).astype(np.float32)
        cache.set("key2", embedding_new, {"value": "key2_value"})

        # Now we should have 2 entries in both cache and FAISS
        assert cache.size() == 2
        assert cache.index.ntotal == 2, "FAISS index should have 2 vectors"

    def test_invalid_dimension(self, cache: SemanticCache) -> None:
        """Test error on invalid embedding dimension."""
        wrong_embedding = np.random.rand(64).astype(np.float32)

        with pytest.raises(ValueError, match="dimension"):
            cache.set("key1", wrong_embedding, {"value": "test"})

        with pytest.raises(ValueError, match="dimension"):
            cache.search(wrong_embedding, k=5)

    def test_normalization(self, cache: SemanticCache) -> None:
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


class TestIVFFlatTraining:
    """Test IVFFlat index training."""

    def test_ivfflat_training(self) -> None:
        """Test that IVFFlat index trains correctly."""
        pytest.importorskip("faiss")

        config = CacheConfig(
            backend=CacheBackend.FAISS,
            dimension=128,
            faiss_index_type="IVFFlat",
            faiss_nlist=10,  # Small nlist for testing
        )
        cache = create_cache(config)

        # Add entries before training threshold
        for i in range(5):
            embedding = np.random.rand(128).astype(np.float32)
            cache.set(f"key_{i}", embedding, {"index": i})

        # Should be buffered
        assert cache.size() == 5

        # Search should work on buffered entries
        query = np.random.rand(128).astype(np.float32)
        results = cache.search(query, k=3, threshold=0.0)
        assert len(results) <= 3

        # Add more entries to trigger training
        for i in range(5, 15):
            embedding = np.random.rand(128).astype(np.float32)
            cache.set(f"key_{i}", embedding, {"index": i})

        # Should be trained now
        assert cache.size() == 15

        # Search should work after training
        results = cache.search(query, k=5, threshold=0.0)
        assert len(results) <= 5

    def test_ivfflat_search_before_training(self) -> None:
        """Test search works before IVFFlat training."""
        pytest.importorskip("faiss")

        config = CacheConfig(
            backend=CacheBackend.FAISS,
            dimension=128,
            faiss_index_type="IVFFlat",
            faiss_nlist=100,  # High threshold
        )
        cache = create_cache(config)

        # Add a few entries (less than nlist)
        embeddings_data = []
        for i in range(10):
            embedding = np.random.rand(128).astype(np.float32)
            cache.set(f"key_{i}", embedding, {"index": i})
            embeddings_data.append((embedding, i))

        # Search for exact match
        for embedding, expected_idx in embeddings_data:
            results = cache.search(embedding, k=1, threshold=0.99)
            assert len(results) == 1
            assert results[0].value["index"] == expected_idx

    def test_ivfflat_training_with_key_overwrites(self) -> None:
        """Test IVFFlat training handles frequent key overwrites correctly.

        This test verifies that when many keys are overwritten before training,
        the cache correctly waits until there are enough active (non-deleted)
        vectors before attempting to train the index.
        """
        pytest.importorskip("faiss")

        config = CacheConfig(
            backend=CacheBackend.FAISS,
            dimension=128,
            faiss_index_type="IVFFlat",
            faiss_nlist=10,  # Requires 10 vectors to train
        )
        cache = create_cache(config)

        # Add 15 entries, but overwrite the same 3 keys repeatedly
        # This simulates a workload with frequent updates
        for i in range(15):
            key = f"key_{i % 3}"  # Only 3 unique keys
            embedding = np.random.rand(128).astype(np.float32)
            cache.set(key, embedding, {"iteration": i})

        # Should have 3 unique keys (not enough to train with nlist=10)
        assert cache.size() == 3

        # Get access to check if trained
        from agdd.optimization.cache import FAISSCache

        assert isinstance(cache, FAISSCache)
        # Should NOT be trained yet (only 3 active vectors < 10 required)
        assert not cache._trained, "Cache should not train with insufficient active vectors"

        # Add more unique keys to reach training threshold
        for i in range(10):
            embedding = np.random.rand(128).astype(np.float32)
            cache.set(f"unique_key_{i}", embedding, {"index": i})

        # Now should have 13 unique keys (3 + 10)
        assert cache.size() == 13

        # Should be trained now (13 active vectors >= 10 required)
        assert cache._trained, "Cache should train after reaching sufficient active vectors"

        # Verify search works correctly after training
        query = np.random.rand(128).astype(np.float32)
        results = cache.search(query, k=5, threshold=0.0)
        assert len(results) <= 5
