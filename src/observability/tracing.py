"""
OpenTelemetry tracing and metrics with Langfuse integration.

This module provides observability instrumentation using OpenTelemetry,
with optional export to Langfuse for LLM-specific observability.

Features:
- Distributed tracing with spans
- Metrics collection (counters, gauges, histograms)
- Structured logging
- Langfuse integration for LLM observability
- Flag-based initialization for testing and development
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

# OpenTelemetry imports (with fallback if not installed)
try:
    from opentelemetry import trace, metrics  # type: ignore[import-not-found]
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter  # type: ignore[import-not-found]
    from opentelemetry.sdk.metrics import MeterProvider  # type: ignore[import-not-found]
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter  # type: ignore[import-not-found]
    from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # type: ignore[import-not-found]
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter  # type: ignore[import-not-found]

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

# Langfuse imports (with fallback if not installed)
try:
    from langfuse import Langfuse  # type: ignore[import-not-found]
    from langfuse.decorators import observe  # type: ignore[import-not-found]

    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    # Stub decorator when Langfuse is not available
    def observe(*args: Any, **kwargs: Any) -> Any:
        def decorator(func: Any) -> Any:
            return func

        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator


logger = logging.getLogger(__name__)


class ObservabilityConfig:
    """Configuration for observability features."""

    def __init__(
        self,
        enable_tracing: bool = True,
        enable_metrics: bool = True,
        enable_langfuse: bool = False,
        service_name: str = "agdd",
        otlp_endpoint: Optional[str] = None,
        langfuse_public_key: Optional[str] = None,
        langfuse_secret_key: Optional[str] = None,
        langfuse_host: Optional[str] = None,
    ):
        """
        Initialize observability configuration.

        Args:
            enable_tracing: Enable OpenTelemetry tracing
            enable_metrics: Enable OpenTelemetry metrics
            enable_langfuse: Enable Langfuse integration
            service_name: Service name for traces/metrics
            otlp_endpoint: OTLP endpoint URL (e.g., http://localhost:4318)
            langfuse_public_key: Langfuse public API key
            langfuse_secret_key: Langfuse secret API key
            langfuse_host: Langfuse host URL (default: https://cloud.langfuse.com)
        """
        self.enable_tracing = enable_tracing
        self.enable_metrics = enable_metrics
        self.enable_langfuse = enable_langfuse
        self.service_name = service_name
        self.otlp_endpoint = otlp_endpoint
        self.langfuse_public_key = langfuse_public_key
        self.langfuse_secret_key = langfuse_secret_key
        self.langfuse_host = langfuse_host or "https://cloud.langfuse.com"

    @classmethod
    def from_env(cls) -> ObservabilityConfig:
        """Create configuration from environment variables."""
        return cls(
            enable_tracing=os.getenv("AGDD_OTEL_TRACING_ENABLED", "false").lower() == "true",
            enable_metrics=os.getenv("AGDD_OTEL_METRICS_ENABLED", "false").lower() == "true",
            enable_langfuse=os.getenv("AGDD_LANGFUSE_ENABLED", "false").lower() == "true",
            service_name=os.getenv("AGDD_SERVICE_NAME", "agdd"),
            otlp_endpoint=os.getenv("AGDD_OTLP_ENDPOINT"),
            langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            langfuse_host=os.getenv("LANGFUSE_HOST"),
        )


class ObservabilityManager:
    """
    Manages OpenTelemetry and Langfuse initialization and lifecycle.

    Singleton pattern for global access.
    """

    _instance: Optional[ObservabilityManager] = None
    _lock = threading.Lock()

    def __init__(self, config: Optional[ObservabilityConfig] = None):
        """
        Initialize observability manager.

        Args:
            config: Observability configuration (defaults to environment-based)
        """
        self.config = config or ObservabilityConfig.from_env()
        self._initialized = False
        self._tracer: Optional[Any] = None
        self._meter: Optional[Any] = None
        self._langfuse_client: Optional[Any] = None

    @classmethod
    def get_instance(cls, config: Optional[ObservabilityConfig] = None) -> ObservabilityManager:
        """Get or create singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        return cls._instance

    def initialize(self) -> None:
        """Initialize all enabled observability backends."""
        with self._lock:
            if self._initialized:
                return

            if not OTEL_AVAILABLE and (
                self.config.enable_tracing or self.config.enable_metrics
            ):
                logger.warning(
                    "OpenTelemetry packages not installed. "
                    "Install with: pip install agdd[observability]"
                )

            if not LANGFUSE_AVAILABLE and self.config.enable_langfuse:
                logger.warning(
                    "Langfuse package not installed. "
                    "Install with: pip install agdd[observability]"
                )

            # Initialize OpenTelemetry tracing
            if self.config.enable_tracing and OTEL_AVAILABLE:
                self._init_tracing()

            # Initialize OpenTelemetry metrics
            if self.config.enable_metrics and OTEL_AVAILABLE:
                self._init_metrics()

            # Initialize Langfuse
            if self.config.enable_langfuse and LANGFUSE_AVAILABLE:
                self._init_langfuse()

            self._initialized = True
            logger.info(
                f"Observability initialized: tracing={self.config.enable_tracing}, "
                f"metrics={self.config.enable_metrics}, langfuse={self.config.enable_langfuse}"
            )

    def _init_tracing(self) -> None:
        """Initialize OpenTelemetry tracing."""
        resource = Resource.create({"service.name": self.config.service_name})
        provider = TracerProvider(resource=resource)

        # Add exporters
        if self.config.otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(endpoint=f"{self.config.otlp_endpoint}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        else:
            # Fallback to console exporter for development
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        trace.set_tracer_provider(provider)
        self._tracer = trace.get_tracer(__name__)
        logger.info("OpenTelemetry tracing initialized")

    def _init_metrics(self) -> None:
        """Initialize OpenTelemetry metrics."""
        resource = Resource.create({"service.name": self.config.service_name})

        # Add metric readers
        if self.config.otlp_endpoint:
            otlp_exporter = OTLPMetricExporter(endpoint=f"{self.config.otlp_endpoint}/v1/metrics")
            reader = PeriodicExportingMetricReader(otlp_exporter, export_interval_millis=60000)
        else:
            # Fallback to console exporter for development
            reader = PeriodicExportingMetricReader(
                ConsoleMetricExporter(), export_interval_millis=60000
            )

        provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(provider)
        self._meter = metrics.get_meter(__name__)
        logger.info("OpenTelemetry metrics initialized")

    def _init_langfuse(self) -> None:
        """Initialize Langfuse client."""
        if not self.config.langfuse_public_key or not self.config.langfuse_secret_key:
            logger.warning(
                "Langfuse enabled but credentials not provided. "
                "Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY."
            )
            return

        self._langfuse_client = Langfuse(
            public_key=self.config.langfuse_public_key,
            secret_key=self.config.langfuse_secret_key,
            host=self.config.langfuse_host,
        )
        logger.info(f"Langfuse initialized: {self.config.langfuse_host}")

    def get_tracer(self) -> Any:
        """Get OpenTelemetry tracer instance."""
        if not self._initialized:
            self.initialize()
        return self._tracer

    def get_meter(self) -> Any:
        """Get OpenTelemetry meter instance."""
        if not self._initialized:
            self.initialize()
        return self._meter

    def get_langfuse_client(self) -> Any:
        """Get Langfuse client instance."""
        if not self._initialized:
            self.initialize()
        return self._langfuse_client

    def shutdown(self) -> None:
        """Shutdown all observability backends."""
        with self._lock:
            if self._langfuse_client is not None:
                self._langfuse_client.flush()
                logger.info("Langfuse client flushed")

            if OTEL_AVAILABLE:
                # Flush any pending spans/metrics
                if self.config.enable_tracing:
                    provider = trace.get_tracer_provider()
                    if hasattr(provider, "shutdown"):
                        provider.shutdown()

                if self.config.enable_metrics:
                    provider = metrics.get_meter_provider()
                    if hasattr(provider, "shutdown"):
                        provider.shutdown()

            self._initialized = False
            logger.info("Observability shutdown complete")


# Convenience functions for global access


def initialize_observability(config: Optional[ObservabilityConfig] = None) -> None:
    """
    Initialize observability with optional configuration.

    Args:
        config: Configuration (defaults to environment-based)
    """
    manager = ObservabilityManager.get_instance(config)
    manager.initialize()


def get_tracer() -> Any:
    """Get global tracer instance."""
    manager = ObservabilityManager.get_instance()
    return manager.get_tracer()


def get_meter() -> Any:
    """Get global meter instance."""
    manager = ObservabilityManager.get_instance()
    return manager.get_meter()


def get_langfuse_client() -> Any:
    """Get global Langfuse client instance."""
    manager = ObservabilityManager.get_instance()
    return manager.get_langfuse_client()


def shutdown_observability() -> None:
    """Shutdown all observability backends."""
    manager = ObservabilityManager.get_instance()
    manager.shutdown()


@contextmanager
def trace_span(name: str, attributes: Optional[Dict[str, Any]] = None) -> Iterator[Any]:
    """
    Context manager for creating a trace span.

    Args:
        name: Span name
        attributes: Optional span attributes

    Usage:
        with trace_span("my_operation", {"key": "value"}) as span:
            # Your code here
            span.set_attribute("result", "success")
    """
    tracer = get_tracer()
    if tracer is None or not OTEL_AVAILABLE:
        # No-op span when tracing is disabled
        class NoOpSpan:
            def set_attribute(self, key: str, value: Any) -> None:
                pass

            def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
                pass

        yield NoOpSpan()
        return

    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield span


# Re-export Langfuse decorator for convenience
__all__ = [
    "ObservabilityConfig",
    "ObservabilityManager",
    "initialize_observability",
    "get_tracer",
    "get_meter",
    "get_langfuse_client",
    "shutdown_observability",
    "trace_span",
    "observe",
]
