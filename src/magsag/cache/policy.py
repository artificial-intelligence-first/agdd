"""Cache TTL and policy configuration utilities.

This module provides functions and configuration for determining cache behavior,
including Time-To-Live (TTL) values based on data sensitivity and content length,
as well as policies for which task types should be cached.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CachePolicyConfig(BaseModel):
    """Configuration for cache TTL and behavior policies.

    Attributes:
        default_ttl: Default TTL in seconds for cached items.
        sensitive_ttl: TTL in seconds for sensitive data (shorter).
        public_ttl: TTL in seconds for public/non-sensitive data (longer).
        max_cacheable_length: Maximum content length in characters to cache.
        enable_caching: Global flag to enable/disable caching.
        cacheable_task_types: Set of task types that should be cached.
    """

    default_ttl: int = Field(default=3600, description="Default TTL in seconds")
    sensitive_ttl: int = Field(
        default=300, description="TTL for sensitive data in seconds"
    )
    public_ttl: int = Field(
        default=7200, description="TTL for public data in seconds"
    )
    max_cacheable_length: int = Field(
        default=50000, description="Maximum content length to cache"
    )
    enable_caching: bool = Field(
        default=True, description="Global caching enabled flag"
    )
    cacheable_task_types: set[str] = Field(
        default_factory=lambda: {
            "completion",
            "embedding",
            "classification",
            "summarization",
            "translation",
        },
        description="Task types that should be cached",
    )


# Global default configuration
_default_config = CachePolicyConfig()


def get_ttl(sensitivity: str = "default", length: int = 0) -> int:
    """Determine the appropriate TTL based on data sensitivity and length.

    Args:
        sensitivity: Sensitivity level - "sensitive", "public", or "default".
        length: Content length in characters. If exceeds max_cacheable_length,
                returns 0 (don't cache).

    Returns:
        TTL in seconds. Returns 0 if content should not be cached.

    Example:
        >>> get_ttl("sensitive", 1000)
        300
        >>> get_ttl("public", 5000)
        7200
        >>> get_ttl("default", 100000)
        0
    """
    config = _default_config

    # Don't cache if content is too long
    if length > config.max_cacheable_length:
        return 0

    if sensitivity == "sensitive":
        return config.sensitive_ttl
    elif sensitivity == "public":
        return config.public_ttl
    else:
        return config.default_ttl


def should_cache(task_type: str) -> bool:
    """Determine if a given task type should be cached.

    Args:
        task_type: The type of task being performed.

    Returns:
        True if the task type should be cached, False otherwise.

    Example:
        >>> should_cache("completion")
        True
        >>> should_cache("streaming_chat")
        False
    """
    config = _default_config

    if not config.enable_caching:
        return False

    return task_type in config.cacheable_task_types


def set_cache_policy_config(config: CachePolicyConfig) -> None:
    """Set the global cache policy configuration.

    This function allows customization of the cache policy for the entire
    application runtime.

    Args:
        config: The new cache policy configuration to use.

    Example:
        >>> custom_config = CachePolicyConfig(
        ...     default_ttl=1800,
        ...     enable_caching=True
        ... )
        >>> set_cache_policy_config(custom_config)
    """
    global _default_config
    _default_config = config


def get_cache_policy_config() -> CachePolicyConfig:
    """Get the current global cache policy configuration.

    Returns:
        The current cache policy configuration.

    Example:
        >>> config = get_cache_policy_config()
        >>> config.default_ttl
        3600
    """
    return _default_config
