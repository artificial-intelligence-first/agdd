"""
Optimization utilities for MAGSAG.

This module provides functionality for:
- SLA-based routing decisions (execution plans, model tier selection)
- LLM API call optimization (batch processing, cost reduction strategies)
- Semantic caching with vector search (FAISS and Redis backends)
- Caching strategies and batching configurations
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from magsag.optimization.optimizer import (
    CostOptimizer,
    ExecutionPlan,
    SLAParameters,
    optimize_for_sla,
)

__all__ = [
    "batch",
    "SLAParameters",
    "ExecutionPlan",
    "CostOptimizer",
    "optimize_for_sla",
]

# Conditional imports for optional cache module
# Cache requires numpy which is an optional dependency
try:
    from magsag.optimization.cache import (  # noqa: F401
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
