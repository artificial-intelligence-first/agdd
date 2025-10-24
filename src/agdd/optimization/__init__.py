"""
Optimization utilities for AGDD.

This module contains utilities for optimizing LLM API calls,
including batch processing, cost reduction strategies, and semantic caching.
"""

from __future__ import annotations

from agdd.optimization.cache import (
    CacheBackend,
    CacheConfig,
    SemanticCache,
    create_cache,
)

__all__ = [
    "batch",
    "CacheBackend",
    "CacheConfig",
    "SemanticCache",
    "create_cache",
]
