"""
Optimization utilities for AGDD.

This module provides functionality for:
- SLA-based routing decisions (execution plans, model tier selection)
- LLM API call optimization (batch processing, cost reduction strategies)
- Caching strategies and batching configurations
"""

from __future__ import annotations

from agdd.optimization.optimizer import (
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
