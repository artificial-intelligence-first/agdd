#!/usr/bin/env python3
"""Benchmark script for semantic cache performance.

Tests cache performance with 1e5 scale entries to verify
that top-K search operates in ms~tens of ms range.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from magsag.optimization.cache import CacheBackend, CacheConfig, create_cache


def benchmark_cache(
    backend: CacheBackend,
    num_entries: int = 100_000,
    dimension: int = 768,
    k: int = 5,
) -> dict[str, Any]:
    """Benchmark cache performance.

    Args:
        backend: Cache backend to test
        num_entries: Number of entries to insert
        dimension: Embedding dimension
        k: Number of results for top-K search

    Returns:
        Dictionary with benchmark results
    """
    print(f"\n{'=' * 60}")
    print(f"Benchmarking {backend.value.upper()} backend")
    print(f"Entries: {num_entries:,} | Dimension: {dimension} | K: {k}")
    print(f"{'=' * 60}\n")

    # Create cache
    config = CacheConfig(
        backend=backend,
        dimension=dimension,
        faiss_index_type="IVFFlat",  # Better for large scale
        faiss_nlist=100,
    )
    cache = create_cache(config)

    # Generate random embeddings
    print(f"Generating {num_entries:,} random embeddings...")
    embeddings = np.random.rand(num_entries, dimension).astype(np.float32)

    # Normalize embeddings
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / norms

    # Insert entries
    print(f"Inserting {num_entries:,} entries...")
    insert_start = time.perf_counter()

    for i in range(num_entries):
        cache.set(
            f"key_{i}",
            embeddings[i],
            {"index": i, "timestamp": time.time()},
        )

        # Progress indicator
        if (i + 1) % 10_000 == 0:
            elapsed = time.perf_counter() - insert_start
            rate = (i + 1) / elapsed
            print(f"  Inserted {i + 1:,} entries ({rate:.1f} entries/sec)")

    insert_time = time.perf_counter() - insert_start
    insert_rate = num_entries / insert_time

    print(f"\n✓ Insert completed in {insert_time:.2f}s ({insert_rate:.1f} entries/sec)")
    print(f"  Cache size: {cache.size():,} entries\n")

    # Perform search queries
    num_queries = 100
    print(f"Performing {num_queries} search queries (k={k})...")

    query_times: list[float] = []
    for i in range(num_queries):
        # Generate random query
        query = np.random.rand(dimension).astype(np.float32)
        query = query / np.linalg.norm(query)

        # Time search
        search_start = time.perf_counter()
        results = cache.search(query, k=k, threshold=0.7)
        search_time = time.perf_counter() - search_start

        query_times.append(search_time * 1000)  # Convert to ms

        if i < 5:  # Show first few results
            print(f"  Query {i + 1}: {search_time * 1000:.2f}ms ({len(results)} results)")

    # Calculate statistics
    avg_time = np.mean(query_times)
    p50_time = np.percentile(query_times, 50)
    p95_time = np.percentile(query_times, 95)
    p99_time = np.percentile(query_times, 99)
    max_time = np.max(query_times)

    print(f"\n{'=' * 60}")
    print("Search Performance Statistics:")
    print(f"{'=' * 60}")
    print(f"  Average:  {avg_time:.2f}ms")
    print(f"  P50:      {p50_time:.2f}ms")
    print(f"  P95:      {p95_time:.2f}ms")
    print(f"  P99:      {p99_time:.2f}ms")
    print(f"  Max:      {max_time:.2f}ms")
    print(f"{'=' * 60}\n")

    # Verify acceptance criteria (ms ~ tens of ms)
    acceptance_threshold_ms = 100.0  # 100ms = tens of ms
    passed = p99_time < acceptance_threshold_ms

    if passed:
        print(f"✅ PASS: P99 latency ({p99_time:.2f}ms) < {acceptance_threshold_ms}ms")
    else:
        print(f"❌ FAIL: P99 latency ({p99_time:.2f}ms) >= {acceptance_threshold_ms}ms")

    return {
        "backend": backend.value,
        "num_entries": num_entries,
        "dimension": dimension,
        "k": k,
        "insert_time_sec": insert_time,
        "insert_rate": insert_rate,
        "avg_search_ms": avg_time,
        "p50_search_ms": p50_time,
        "p95_search_ms": p95_time,
        "p99_search_ms": p99_time,
        "max_search_ms": max_time,
        "passed": passed,
    }


def main() -> None:
    """Run benchmarks."""
    import argparse

    parser = argparse.ArgumentParser(description="Benchmark semantic cache")
    parser.add_argument(
        "--backend",
        choices=["faiss", "redis", "all"],
        default="faiss",
        help="Backend to benchmark",
    )
    parser.add_argument(
        "--entries",
        type=int,
        default=100_000,
        help="Number of entries",
    )
    parser.add_argument(
        "--dimension",
        type=int,
        default=768,
        help="Embedding dimension",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Top-K results",
    )

    args = parser.parse_args()

    results = []

    if args.backend in ("faiss", "all"):
        try:
            result = benchmark_cache(
                CacheBackend.FAISS,
                num_entries=args.entries,
                dimension=args.dimension,
                k=args.k,
            )
            results.append(result)
        except ImportError as e:
            print(f"⚠ Skipping FAISS benchmark: {e}")

    if args.backend in ("redis", "all"):
        try:
            result = benchmark_cache(
                CacheBackend.REDIS,
                num_entries=args.entries,
                dimension=args.dimension,
                k=args.k,
            )
            results.append(result)
        except ImportError as e:
            print(f"⚠ Skipping Redis benchmark: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)
    for result in results:
        status = "✅ PASS" if result["passed"] else "❌ FAIL"
        print(
            f"{status} {result['backend'].upper()}: "
            f"P99={result['p99_search_ms']:.2f}ms "
            f"({result['num_entries']:,} entries)"
        )
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
