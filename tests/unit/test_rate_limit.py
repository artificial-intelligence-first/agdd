"""Unit tests for rate limiting."""
from __future__ import annotations

import time

import pytest

from agdd.api.rate_limit import InMemoryRateLimiter


def test_in_memory_rate_limiter_allows_requests_within_limit() -> None:
    """Test that requests within rate limit are allowed."""
    limiter = InMemoryRateLimiter(qps=2)  # 2 requests per second

    # Should allow first 2 requests
    limiter.check_rate_limit("test-key")
    limiter.check_rate_limit("test-key")


def test_in_memory_rate_limiter_blocks_requests_exceeding_limit() -> None:
    """Test that requests exceeding rate limit are blocked."""
    limiter = InMemoryRateLimiter(qps=2)

    # First 2 requests should succeed
    limiter.check_rate_limit("test-key")
    limiter.check_rate_limit("test-key")

    # Third request should fail
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        limiter.check_rate_limit("test-key")

    assert exc_info.value.status_code == 429
    assert "rate_limit_exceeded" in str(exc_info.value.detail)


def test_in_memory_rate_limiter_refills_tokens_over_time() -> None:
    """Test that tokens are refilled over time."""
    limiter = InMemoryRateLimiter(qps=5)  # 5 requests per second

    # Exhaust tokens
    for _ in range(5):
        limiter.check_rate_limit("test-key")

    # Should fail immediately
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        limiter.check_rate_limit("test-key")

    # Wait for tokens to refill (0.5 seconds = 2.5 tokens)
    time.sleep(0.5)

    # Should now allow 2 more requests
    limiter.check_rate_limit("test-key")
    limiter.check_rate_limit("test-key")


def test_in_memory_rate_limiter_separate_keys() -> None:
    """Test that different keys have separate rate limits."""
    limiter = InMemoryRateLimiter(qps=2)

    # Each key should have its own bucket
    limiter.check_rate_limit("key-1")
    limiter.check_rate_limit("key-1")  # Exhaust key-1

    # Other keys should still work
    limiter.check_rate_limit("key-2")
    limiter.check_rate_limit("key-3")


def test_in_memory_rate_limiter_respects_qps() -> None:
    """Test that rate limiter respects configured QPS."""
    limiter = InMemoryRateLimiter(qps=10)

    # Should allow 10 requests
    for _ in range(10):
        limiter.check_rate_limit("test-key")

    # 11th should fail
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        limiter.check_rate_limit("test-key")


def test_rate_limiter_error_message() -> None:
    """Test that rate limit error has proper message."""
    limiter = InMemoryRateLimiter(qps=2)

    # Exhaust tokens
    limiter.check_rate_limit("test-key")
    limiter.check_rate_limit("test-key")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        limiter.check_rate_limit("test-key")

    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "rate_limit_exceeded"
    assert "2 requests per second" in detail["message"]
