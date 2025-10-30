"""Core types and Service Provider Interfaces (SPI) for AGDD.

This module provides foundational Intermediate Representation (IR) types and
extensibility points for pluggable providers (LLM, observability, policy).
"""

from __future__ import annotations

from agdd.core.types import CapabilityMatrix, PlanIR, PolicySnapshot, RunIR

__all__ = [
    "CapabilityMatrix",
    "PlanIR",
    "PolicySnapshot",
    "RunIR",
]
