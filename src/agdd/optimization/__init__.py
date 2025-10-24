"""
Optimization utilities for AGDD.

This module contains utilities for optimizing LLM API calls,
including batch processing, cost reduction strategies, and semantic caching.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["batch"]

# Conditional imports for optional cache module
# Cache requires numpy which is an optional dependency
try:
    from agdd.optimization.cache import (  # noqa: F401
        CacheBackend,
        CacheConfig,
        SemanticCache,
        create_cache,
    )

    __all__.extend(["CacheBackend", "CacheConfig", "SemanticCache", "create_cache"])
except ImportError:
    # Cache module not available (numpy not installed)
    if not TYPE_CHECKING:
        pass
