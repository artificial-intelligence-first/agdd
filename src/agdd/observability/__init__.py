"""Observability utilities for AGDD."""

from __future__ import annotations

from .cost_tracker import (
    DEFAULT_COSTS_DIR,
    DEFAULT_DB_PATH,
    DEFAULT_JSONL_PATH,
    DEFAULT_RUNS_DIR,
    CostRecord,
    CostSummary,
    CostTracker,
    get_tracker,
    record_llm_cost,
)
from .summarize_runs import summarize
from .tracing import (
    ObservabilityConfig,
    ObservabilityManager,
    initialize_observability,
    observe,
    shutdown_observability,
)

__all__ = [
    "DEFAULT_RUNS_DIR",
    "DEFAULT_COSTS_DIR",
    "DEFAULT_JSONL_PATH",
    "DEFAULT_DB_PATH",
    "CostRecord",
    "CostSummary",
    "CostTracker",
    "get_tracker",
    "record_llm_cost",
    "summarize",
    "ObservabilityConfig",
    "ObservabilityManager",
    "initialize_observability",
    "observe",
    "shutdown_observability",
]
