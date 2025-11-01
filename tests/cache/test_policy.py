"""Tests for cache policy utilities."""

from __future__ import annotations

from magsag.cache.policy import (
    CachePolicyConfig,
    get_cache_policy_config,
    get_ttl,
    set_cache_policy_config,
    should_cache,
)


class TestCachePolicyConfig:
    """Test cases for CachePolicyConfig model."""

    def test_default_config(self) -> None:
        """Test that default configuration is valid."""
        config = CachePolicyConfig()
        assert config.default_ttl == 3600
        assert config.sensitive_ttl == 300
        assert config.public_ttl == 7200
        assert config.max_cacheable_length == 50000
        assert config.enable_caching is True
        assert "completion" in config.cacheable_task_types

    def test_custom_config(self) -> None:
        """Test creating custom configuration."""
        config = CachePolicyConfig(
            default_ttl=1800,
            sensitive_ttl=600,
            public_ttl=3600,
            max_cacheable_length=100000,
            enable_caching=False,
            cacheable_task_types={"custom_task"},
        )
        assert config.default_ttl == 1800
        assert config.sensitive_ttl == 600
        assert config.public_ttl == 3600
        assert config.max_cacheable_length == 100000
        assert config.enable_caching is False
        assert config.cacheable_task_types == {"custom_task"}

    def test_partial_config(self) -> None:
        """Test creating configuration with partial overrides."""
        config = CachePolicyConfig(default_ttl=1200)
        assert config.default_ttl == 1200
        assert config.sensitive_ttl == 300  # default value


class TestGetTTL:
    """Test cases for get_ttl function."""

    def test_default_ttl(self) -> None:
        """Test default TTL value."""
        ttl = get_ttl("default", 1000)
        assert ttl == 3600

    def test_sensitive_ttl(self) -> None:
        """Test sensitive data TTL."""
        ttl = get_ttl("sensitive", 1000)
        assert ttl == 300

    def test_public_ttl(self) -> None:
        """Test public data TTL."""
        ttl = get_ttl("public", 1000)
        assert ttl == 7200

    def test_length_limit_exceeded(self) -> None:
        """Test that content exceeding max length returns TTL of 0."""
        ttl = get_ttl("default", 100000)
        assert ttl == 0

    def test_length_at_boundary(self) -> None:
        """Test content length at exact boundary."""
        ttl = get_ttl("default", 50000)
        assert ttl == 3600

    def test_length_just_over_boundary(self) -> None:
        """Test content length just over boundary."""
        ttl = get_ttl("default", 50001)
        assert ttl == 0

    def test_zero_length(self) -> None:
        """Test with zero length content."""
        ttl = get_ttl("default", 0)
        assert ttl == 3600

    def test_negative_length(self) -> None:
        """Test with negative length (edge case)."""
        ttl = get_ttl("default", -1)
        assert ttl == 3600

    def test_unknown_sensitivity(self) -> None:
        """Test that unknown sensitivity falls back to default."""
        ttl = get_ttl("unknown", 1000)
        assert ttl == 3600


class TestShouldCache:
    """Test cases for should_cache function."""

    def test_cacheable_task_types(self) -> None:
        """Test that default cacheable task types return True."""
        assert should_cache("completion") is True
        assert should_cache("embedding") is True
        assert should_cache("classification") is True
        assert should_cache("summarization") is True
        assert should_cache("translation") is True

    def test_non_cacheable_task_type(self) -> None:
        """Test that non-cacheable task types return False."""
        assert should_cache("streaming_chat") is False
        assert should_cache("unknown_task") is False
        assert should_cache("") is False

    def test_caching_disabled_globally(self) -> None:
        """Test that caching disabled returns False for all tasks."""
        # Save original config
        original_config = get_cache_policy_config()

        try:
            # Set config with caching disabled
            config = CachePolicyConfig(enable_caching=False)
            set_cache_policy_config(config)

            assert should_cache("completion") is False
            assert should_cache("embedding") is False
        finally:
            # Restore original config
            set_cache_policy_config(original_config)

    def test_custom_cacheable_types(self) -> None:
        """Test custom cacheable task types."""
        # Save original config
        original_config = get_cache_policy_config()

        try:
            # Set config with custom task types
            config = CachePolicyConfig(
                cacheable_task_types={"custom_task", "another_task"}
            )
            set_cache_policy_config(config)

            assert should_cache("custom_task") is True
            assert should_cache("another_task") is True
            assert should_cache("completion") is False  # Not in custom set
        finally:
            # Restore original config
            set_cache_policy_config(original_config)


class TestSetGetCachePolicyConfig:
    """Test cases for config getter/setter functions."""

    def test_get_default_config(self) -> None:
        """Test getting the default configuration."""
        config = get_cache_policy_config()
        assert isinstance(config, CachePolicyConfig)
        assert config.enable_caching is True

    def test_set_and_get_config(self) -> None:
        """Test setting and getting configuration."""
        # Save original config
        original_config = get_cache_policy_config()

        try:
            # Set custom config
            custom_config = CachePolicyConfig(
                default_ttl=999,
                enable_caching=False,
            )
            set_cache_policy_config(custom_config)

            # Get and verify
            retrieved_config = get_cache_policy_config()
            assert retrieved_config.default_ttl == 999
            assert retrieved_config.enable_caching is False
        finally:
            # Restore original config
            set_cache_policy_config(original_config)

    def test_config_persistence_across_calls(self) -> None:
        """Test that config changes persist across function calls."""
        # Save original config
        original_config = get_cache_policy_config()

        try:
            # Set custom config
            custom_config = CachePolicyConfig(sensitive_ttl=123)
            set_cache_policy_config(custom_config)

            # Verify TTL uses new config
            ttl = get_ttl("sensitive", 100)
            assert ttl == 123
        finally:
            # Restore original config
            set_cache_policy_config(original_config)


class TestIntegration:
    """Integration tests for cache policy module."""

    def test_policy_workflow(self) -> None:
        """Test a complete workflow with policy decisions."""
        # Check if task should be cached
        if should_cache("completion"):
            # Determine appropriate TTL
            ttl = get_ttl("default", 5000)
            assert ttl > 0

            # Sensitive data should have shorter TTL
            sensitive_ttl = get_ttl("sensitive", 5000)
            assert sensitive_ttl < ttl

    def test_policy_with_custom_config(self) -> None:
        """Test policy workflow with custom configuration."""
        # Save original config
        original_config = get_cache_policy_config()

        try:
            # Setup custom policy
            custom_config = CachePolicyConfig(
                default_ttl=1000,
                sensitive_ttl=100,
                max_cacheable_length=10000,
                cacheable_task_types={"special_task"},
            )
            set_cache_policy_config(custom_config)

            # Test custom policy
            assert should_cache("special_task") is True
            assert should_cache("completion") is False
            assert get_ttl("default", 5000) == 1000
            assert get_ttl("default", 15000) == 0  # Over limit
        finally:
            # Restore original config
            set_cache_policy_config(original_config)
