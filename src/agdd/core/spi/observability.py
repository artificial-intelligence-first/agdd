"""Observability SPI for telemetry and tracing integration.

This module defines the ObservabilityProvider protocol that telemetry backends
must implement, enabling pluggable integrations for metrics, traces, and events
with consistent instrumentation across AGDD components.
"""

from __future__ import annotations

from typing import Any, Protocol

from agdd.core.types import RunIR


class ObservabilityProvider(Protocol):
    """Protocol for observability and telemetry provider implementations.

    Implementations integrate with telemetry systems (OpenTelemetry, DataDog, etc.)
    to emit metrics, traces, and structured events for monitoring and debugging.
    """

    async def emit_event(
        self,
        event_type: str,
        run_ir: RunIR,
        payload: dict[str, Any],
        *,
        timestamp: float | None = None,
    ) -> None:
        """Emit a structured event for the given run.

        Args:
            event_type: Event type identifier (e.g., 'run.started', 'run.completed',
                'tool.invoked', 'policy.evaluated').
            run_ir: Complete run context for event attribution and filtering.
            payload: Event-specific payload dictionary with arbitrary metadata.
            timestamp: Optional Unix timestamp (seconds since epoch); defaults to
                current time if not provided.

        Note:
            Events should be emitted asynchronously without blocking the caller.
            Implementations may batch events for efficiency.
        """
        ...

    async def record_metric(
        self,
        metric_name: str,
        value: float,
        *,
        tags: dict[str, str] | None = None,
        timestamp: float | None = None,
    ) -> None:
        """Record a numeric metric value with optional tags.

        Args:
            metric_name: Metric identifier in dot-notation (e.g., 'run.latency_ms',
                'cost.total_usd', 'provider.tokens_used').
            value: Numeric metric value (counter, gauge, histogram sample, etc.).
            tags: Optional key-value tags for metric dimensions (provider, model,
                agent, status, etc.).
            timestamp: Optional Unix timestamp; defaults to current time.

        Note:
            Implementations should handle metric aggregation and cardinality
            management according to backend capabilities.
        """
        ...

    async def start_span(
        self,
        span_name: str,
        run_ir: RunIR,
        *,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        """Start a distributed tracing span for a logical operation.

        Args:
            span_name: Human-readable span name (e.g., 'provider.generate',
                'policy.evaluate', 'tool.execute').
            run_ir: Run context for span attribution and trace correlation.
            parent_span_id: Optional parent span identifier for nested spans.
            attributes: Optional span attributes (tags, metadata).

        Returns:
            Unique span identifier that must be passed to end_span().

        Note:
            Spans should follow OpenTelemetry semantic conventions where applicable.
        """
        ...

    async def end_span(
        self,
        span_id: str,
        *,
        status: str = "ok",
        error: Exception | None = None,
    ) -> None:
        """End a distributed tracing span started by start_span().

        Args:
            span_id: Span identifier returned from start_span().
            status: Span status - "ok" for success, "error" for failure.
            error: Optional exception object if span ended due to error.

        Note:
            Ending a span triggers span export to the telemetry backend.
            Implementations should handle gracefully if span_id is unknown.
        """
        ...

    async def flush(self) -> None:
        """Flush all pending telemetry data to the backend.

        Blocks until all queued events, metrics, and spans are sent or timeout.
        Should be called during graceful shutdown to ensure data completeness.

        Raises:
            RuntimeError: If flush fails or times out.
        """
        ...
