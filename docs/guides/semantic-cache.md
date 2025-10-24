# Semantic Cache Guide

AGDD provides semantic caching using vector similarity search to reduce costs and latency by reusing responses for similar prompts.

## Overview

The semantic cache system offers:

- **Vector similarity search**: Top-K nearest neighbor search (no O(N) linear scans)
- **Multiple backends**: FAISS (local) and Redis Vector Index (distributed)
- **Automatic cache hit detection**: Find semantically similar queries
- **Cost savings**: Avoid redundant LLM calls for similar prompts
- **Flexible configuration**: Tune similarity thresholds and cache sizes

## Architecture

### How It Works

1. **Embed query**: Convert prompt to vector embedding (e.g., using OpenAI embeddings)
2. **Search cache**: Find top-K similar entries using vector index
3. **Threshold check**: If similarity exceeds threshold, return cached result
4. **Cache update**: Store new query-response pairs for future reuse

### No O(N) Scans

Unlike naive caching that scans all entries, AGDD uses:

- **FAISS**: Approximate Nearest Neighbor (ANN) with IndexIVFFlat or IndexFlat
- **Redis**: RediSearch vector similarity with HNSW indexing

Both provide sub-linear search time, making cache lookups efficient even with millions of entries.

## Quick Start

### Installation

```bash
# FAISS backend (default)
pip install 'agdd[faiss]'

# Redis backend (production)
pip install 'agdd[redis]'
```

### Basic Usage

```python
from agdd.optimization.cache import create_cache, CacheConfig
import numpy as np

# Create cache with FAISS backend
config = CacheConfig(
    backend="faiss",
    dimension=768,  # Match embedding dimension
    faiss_index_type="Flat"  # or "IVFFlat" for large datasets
)
cache = create_cache(config)

# Store entry
embedding = np.random.rand(768).astype(np.float32)
cache.set(
    key="query_hash_123",
    embedding=embedding,
    value={"response": "Cached LLM response", "metadata": {}}
)

# Search for similar entries
query_embedding = np.random.rand(768).astype(np.float32)
matches = cache.search(
    query_embedding=query_embedding,
    k=5,  # Return top 5 matches
    threshold=0.9  # 90% similarity required
)

for match in matches:
    print(f"Key: {match.key}, Distance: {match.distance:.4f}")
    print(f"Cached value: {match.value}")
```

## Backend Configuration

### FAISS Backend (Local)

**Best for**: Development, single-node deployments, offline caching

```python
from agdd.optimization.cache import CacheConfig, create_cache

# Exact search (slower, 100% accuracy)
config_flat = CacheConfig(
    backend="faiss",
    dimension=768,
    faiss_index_type="Flat"
)
cache_flat = create_cache(config_flat)

# Approximate search (faster, good accuracy)
config_ivf = CacheConfig(
    backend="faiss",
    dimension=1536,  # e.g., OpenAI text-embedding-3-large
    faiss_index_type="IVFFlat",
    faiss_nlist=100  # Number of clusters
)
cache_ivf = create_cache(config_ivf)
```

**IVFFlat Configuration**:
- `faiss_nlist`: Number of clusters (recommended: sqrt(N) for N entries)
- Requires training with at least `nlist` vectors before search
- Trade-off: Higher nlist = slower build, faster search

### Redis Backend (Distributed)

**Best for**: Production, multi-node deployments, shared cache

```python
from agdd.optimization.cache import CacheConfig, create_cache

config = CacheConfig(
    backend="redis",
    dimension=768,
    redis_url="redis://localhost:6379",
    redis_index_name="agdd_cache"
)
cache = create_cache(config)

# Redis uses HNSW indexing automatically
# Persists across restarts
# Supports concurrent access from multiple processes
```

**Redis Requirements**:
- Redis Stack or Redis with RediSearch module
- Installation: `docker run -p 6379:6379 redis/redis-stack-server:latest`

### Environment Variables

```bash
# Backend selection
export AGDD_CACHE_BACKEND="faiss"  # or "redis"
export AGDD_CACHE_DIMENSION=768

# Redis configuration
export AGDD_CACHE_REDIS_URL="redis://localhost:6379"
export AGDD_CACHE_REDIS_INDEX_NAME="agdd_cache"

# FAISS configuration
export AGDD_CACHE_FAISS_INDEX_TYPE="IVFFlat"
export AGDD_CACHE_FAISS_NLIST=100
```

## Integration with Agent Code

### Embedding Generation

Generate embeddings using OpenAI:

```python
from openai import OpenAI
import numpy as np

client = OpenAI()

def get_embedding(text: str, model: str = "text-embedding-3-small") -> np.ndarray:
    """Generate embedding for text."""
    response = client.embeddings.create(
        model=model,
        input=text
    )
    embedding = np.array(response.data[0].embedding, dtype=np.float32)

    # Normalize for cosine similarity
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm

    return embedding
```

### Cache-Aware Agent

```python
from agdd.optimization.cache import get_cache, CacheConfig
import hashlib
import json

def run(payload: dict, **deps) -> dict:
    # Get or create cache
    cache_config = CacheConfig(backend="faiss", dimension=1536)
    cache = get_cache(cache_config)

    # Generate query embedding
    prompt = payload.get("prompt", "")
    query_embedding = get_embedding(prompt, model="text-embedding-3-small")

    # Search cache
    matches = cache.search(
        query_embedding=query_embedding,
        k=1,
        threshold=0.95  # 95% similarity
    )

    # Cache hit
    if matches:
        cached_result = matches[0].value
        deps['obs'].log({
            "event": "cache_hit",
            "cached_key": matches[0].key,
            "similarity": 1.0 - matches[0].distance
        })
        return cached_result

    # Cache miss - call LLM
    deps['obs'].log({"event": "cache_miss"})
    result = deps['skills'].invoke("llm.completion", payload)

    # Store in cache
    query_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    cache.set(
        key=f"llm_{query_hash}",
        embedding=query_embedding,
        value=result
    )

    return result
```

## Routing Integration

### Plan-Based Caching

Enable caching via routing policy:

```yaml
# catalog/policies/cost_optimized.yaml
name: cost-optimized
description: Routing with aggressive caching

routes:
  - task_type: qa-retrieval
    provider: openai
    model: gpt-4o-mini
    use_batch: false
    use_cache: true  # Enable semantic cache
    structured_output: false
    moderation: false
    metadata:
      cache_threshold: 0.92

defaults:
  use_cache: true
  metadata:
    cache_threshold: 0.90
```

### Auto-Cache Wrapper

```python
from functools import wraps
from agdd.optimization.cache import get_cache

def with_semantic_cache(threshold: float = 0.9):
    """Decorator to add semantic caching to functions."""
    cache = get_cache()

    def decorator(func):
        @wraps(func)
        def wrapper(prompt: str, **kwargs):
            embedding = get_embedding(prompt)

            # Check cache
            matches = cache.search(embedding, k=1, threshold=threshold)
            if matches:
                return matches[0].value

            # Call function
            result = func(prompt, **kwargs)

            # Update cache
            cache.set(
                key=f"{func.__name__}_{hash(prompt)}",
                embedding=embedding,
                value=result
            )

            return result

        return wrapper
    return decorator

@with_semantic_cache(threshold=0.95)
def generate_summary(prompt: str) -> dict:
    # LLM call logic
    pass
```

## Advanced Features

### Cache Warmup

Pre-populate cache with common queries:

```python
from agdd.optimization.cache import get_cache

cache = get_cache()

# Warmup data
common_queries = [
    ("What is Python?", {"response": "Python is a programming language..."}),
    ("Explain machine learning", {"response": "Machine learning is..."}),
]

for query, response in common_queries:
    embedding = get_embedding(query)
    cache.set(
        key=f"warmup_{hash(query)}",
        embedding=embedding,
        value=response
    )

print(f"Cache warmed up with {cache.size()} entries")
```

### Cache Statistics

```python
from agdd.optimization.cache import get_cache

cache = get_cache()

# Get cache size
print(f"Cache entries: {cache.size()}")

# Clear cache
cache.clear()
print("Cache cleared")
```

### TTL and Eviction (Redis)

```python
# Redis backend supports TTL via key expiration
import redis

r = redis.from_url("redis://localhost:6379")

# Set TTL on cached keys
cache_key = "agdd_cache:query_123"
r.expire(cache_key, 3600)  # Expire after 1 hour
```

## Cost Optimization

### Cache Hit Rate

Track cache effectiveness:

```python
class CacheMetrics:
    def __init__(self):
        self.hits = 0
        self.misses = 0

    def hit(self):
        self.hits += 1

    def miss(self):
        self.misses += 1

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def savings_pct(self) -> float:
        # Estimate cost savings (assuming cache eliminates LLM call)
        return self.hit_rate * 100

metrics = CacheMetrics()

# Track in agent code
matches = cache.search(embedding, k=1, threshold=0.9)
if matches:
    metrics.hit()
else:
    metrics.miss()

print(f"Cache hit rate: {metrics.hit_rate:.1%}")
print(f"Estimated savings: {metrics.savings_pct:.1f}%")
```

### Embedding Costs

Consider embedding API costs:

```python
# OpenAI embedding costs (as of 2025-01)
EMBEDDING_COSTS = {
    "text-embedding-3-small": 0.02 / 1_000_000,  # $0.02 per 1M tokens
    "text-embedding-3-large": 0.13 / 1_000_000,  # $0.13 per 1M tokens
}

# Calculate break-even point
llm_cost_per_call = 0.01  # e.g., gpt-4o-mini
embedding_cost = EMBEDDING_COSTS["text-embedding-3-small"] * 100  # ~100 tokens

break_even_hits = embedding_cost / llm_cost_per_call
print(f"Break-even: {break_even_hits:.2f} cache hits per query")
```

## Performance Tuning

### Similarity Threshold Selection

```python
# High precision (fewer false positives)
cache.search(embedding, k=5, threshold=0.95)

# Balanced
cache.search(embedding, k=5, threshold=0.90)

# High recall (more cache hits, may include dissimilar queries)
cache.search(embedding, k=5, threshold=0.85)
```

### FAISS Index Selection

| Index Type | Speed | Memory | Accuracy | Use Case |
|------------|-------|--------|----------|----------|
| Flat       | Slow  | High   | 100%     | Small datasets (<10K) |
| IVFFlat    | Fast  | Medium | 95-99%   | Large datasets (>10K) |

### Redis Tuning

```python
# Increase connection pool for concurrent access
import redis

pool = redis.ConnectionPool(
    host='localhost',
    port=6379,
    max_connections=50
)
r = redis.Redis(connection_pool=pool)
```

## Best Practices

1. **Normalize embeddings**: Always normalize vectors before storing/searching
2. **Choose appropriate threshold**: Balance precision and recall
3. **Monitor hit rate**: Track cache effectiveness over time
4. **Clear stale entries**: Implement TTL or periodic cleanup
5. **Use appropriate backend**: FAISS for dev, Redis for production
6. **Consider embedding costs**: Factor into total cost calculations

## References

- [FAISS Documentation](https://github.com/facebookresearch/faiss/wiki)
- [Redis Vector Similarity](https://redis.io/docs/stack/search/reference/vectors/)
- [OpenAI Embeddings Guide](https://platform.openai.com/docs/guides/embeddings)
- [AGDD Cost Optimization](./cost-optimization.md)
- [AGDD Routing Guide](./routing.md)
