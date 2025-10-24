"""Tests for OpenTelemetry and Langfuse integration."""

from __future__ import annotations


import pytest

from observability.tracing import (
    ObservabilityConfig,
    ObservabilityManager,
    initialize_observability,
    get_tracer,
    get_meter,
    get_langfuse_client,
    shutdown_observability,
    trace_span,
)


@pytest.fixture(autouse=True)
def reset_observability() -> None:
    """Reset observability manager singleton between tests."""
    # Reset singleton instance
    ObservabilityManager._instance = None
    yield
    # Shutdown after test
    if ObservabilityManager._instance is not None:
        shutdown_observability()
    ObservabilityManager._instance = None


@pytest.fixture
def disabled_config() -> ObservabilityConfig:
    """Configuration with all features disabled."""
    return ObservabilityConfig(
        enable_tracing=False,
        enable_metrics=False,
        enable_langfuse=False,
    )


@pytest.fixture
def tracing_only_config() -> ObservabilityConfig:
    """Configuration with only tracing enabled."""
    return ObservabilityConfig(
        enable_tracing=True,
        enable_metrics=False,
        enable_langfuse=False,
        service_name="test-service",
    )


def test_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test configuration loading from environment variables."""
    monkeypatch.setenv("AGDD_OTEL_TRACING_ENABLED", "true")
    monkeypatch.setenv("AGDD_OTEL_METRICS_ENABLED", "true")
    monkeypatch.setenv("AGDD_LANGFUSE_ENABLED", "false")
    monkeypatch.setenv("AGDD_SERVICE_NAME", "my-service")
    monkeypatch.setenv("AGDD_OTLP_ENDPOINT", "http://localhost:4318")

    config = ObservabilityConfig.from_env()

    assert config.enable_tracing is True
    assert config.enable_metrics is True
    assert config.enable_langfuse is False
    assert config.service_name == "my-service"
    assert config.otlp_endpoint == "http://localhost:4318"


def test_config_defaults() -> None:
    """Test default configuration values."""
    config = ObservabilityConfig()

    assert config.enable_tracing is True
    assert config.enable_metrics is True
    assert config.enable_langfuse is False
    assert config.service_name == "agdd"
    assert config.otlp_endpoint is None
    assert config.langfuse_host == "https://cloud.langfuse.com"


def test_manager_singleton() -> None:
    """Test that ObservabilityManager is a singleton."""
    manager1 = ObservabilityManager.get_instance()
    manager2 = ObservabilityManager.get_instance()

    assert manager1 is manager2


def test_initialize_with_disabled_config(disabled_config: ObservabilityConfig) -> None:
    """Test initialization with all features disabled."""
    manager = ObservabilityManager.get_instance(disabled_config)
    manager.initialize()

    assert manager._initialized is True
    assert manager.get_tracer() is None
    assert manager.get_meter() is None
    assert manager.get_langfuse_client() is None


def test_initialize_tracing_without_packages(
    tracing_only_config: ObservabilityConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test initialization when OpenTelemetry packages are not installed."""
    # Mock OTEL_AVAILABLE as False
    import observability.tracing as tracing_module

    monkeypatch.setattr(tracing_module, "OTEL_AVAILABLE", False)

    manager = ObservabilityManager.get_instance(tracing_only_config)
    manager.initialize()

    # Should not raise, but tracer should be None
    assert manager.get_tracer() is None


def test_initialize_langfuse_without_credentials() -> None:
    """Test that Langfuse initialization warns when credentials are missing."""
    config = ObservabilityConfig(
        enable_langfuse=True,
        langfuse_public_key=None,
        langfuse_secret_key=None,
    )

    manager = ObservabilityManager.get_instance(config)
    manager.initialize()

    # Should initialize but client should be None due to missing credentials
    assert manager.get_langfuse_client() is None


def test_get_tracer_initializes_if_needed(disabled_config: ObservabilityConfig) -> None:
    """Test that get_tracer initializes manager if not already initialized."""
    manager = ObservabilityManager.get_instance(disabled_config)
    assert manager._initialized is False

    tracer = manager.get_tracer()

    assert manager._initialized is True
    assert tracer is None  # Disabled config


def test_shutdown_flushes_resources(disabled_config: ObservabilityConfig) -> None:
    """Test that shutdown properly cleans up resources."""
    manager = ObservabilityManager.get_instance(disabled_config)
    manager.initialize()

    assert manager._initialized is True

    manager.shutdown()

    assert manager._initialized is False


def test_global_convenience_functions(disabled_config: ObservabilityConfig) -> None:
    """Test global convenience functions."""
    initialize_observability(disabled_config)

    tracer = get_tracer()
    meter = get_meter()
    client = get_langfuse_client()

    assert tracer is None
    assert meter is None
    assert client is None

    shutdown_observability()


def test_trace_span_context_manager_disabled() -> None:
    """Test trace_span context manager when tracing is disabled."""
    config = ObservabilityConfig(enable_tracing=False)
    initialize_observability(config)

    # Should not raise even when disabled
    with trace_span("test_operation", {"key": "value"}) as span:
        # Span should be a no-op
        span.set_attribute("result", "success")
        span.add_event("test_event")

    # No assertions needed - just verify it doesn't crash


def test_trace_span_with_attributes() -> None:
    """Test trace_span with attributes when tracing is enabled."""
    # Note: This test requires OpenTelemetry to be installed
    # If not installed, trace_span will use no-op span
    config = ObservabilityConfig(
        enable_tracing=True,
        enable_metrics=False,
        enable_langfuse=False,
    )
    initialize_observability(config)

    with trace_span("test_span", {"attr1": "value1", "attr2": 42}) as span:
        # Should not raise
        span.set_attribute("result", "completed")

    # Verify no crashes


def test_manager_thread_safety() -> None:
    """Test that manager initialization is thread-safe."""
    import threading

    results: list[ObservabilityManager] = []

    def get_manager() -> None:
        manager = ObservabilityManager.get_instance()
        results.append(manager)

    threads = [threading.Thread(target=get_manager) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # All threads should get the same instance
    assert len(set(id(m) for m in results)) == 1


def test_multiple_initializations_are_idempotent(disabled_config: ObservabilityConfig) -> None:
    """Test that multiple initialize calls are safe."""
    manager = ObservabilityManager.get_instance(disabled_config)

    manager.initialize()
    manager.initialize()
    manager.initialize()

    # Should only initialize once
    assert manager._initialized is True


def test_observe_decorator_available() -> None:
    """Test that observe decorator is available."""
    from observability.tracing import observe

    # Should be importable
    assert observe is not None

    # Test stub decorator when Langfuse is not available
    @observe
    def test_function() -> str:
        return "test"

    result = test_function()
    assert result == "test"


def test_langfuse_config_with_custom_host() -> None:
    """Test Langfuse configuration with custom host."""
    config = ObservabilityConfig(
        enable_langfuse=True,
        langfuse_public_key="pk_test",
        langfuse_secret_key="sk_test",
        langfuse_host="https://custom.langfuse.host",
    )

    assert config.langfuse_host == "https://custom.langfuse.host"


def test_config_from_env_with_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test configuration from env with Langfuse variables."""
    monkeypatch.setenv("AGDD_LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk_env_test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk_env_test")
    monkeypatch.setenv("LANGFUSE_HOST", "https://env.langfuse.host")

    config = ObservabilityConfig.from_env()

    assert config.enable_langfuse is True
    assert config.langfuse_public_key == "pk_env_test"
    assert config.langfuse_secret_key == "sk_env_test"
    assert config.langfuse_host == "https://env.langfuse.host"
