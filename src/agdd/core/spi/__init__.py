"""Service Provider Interfaces (SPI) for AGDD extensibility.

This package defines protocol interfaces for pluggable implementations:
- Provider: LLM provider abstraction for multi-modal generation
- ObservabilityProvider: Telemetry and tracing integration points
- PolicyProvider: Policy evaluation and enforcement hooks
"""

from __future__ import annotations

from agdd.core.spi.observability import ObservabilityProvider
from agdd.core.spi.policy import PolicyProvider
from agdd.core.spi.provider import Provider

__all__ = [
    "ObservabilityProvider",
    "PolicyProvider",
    "Provider",
]
