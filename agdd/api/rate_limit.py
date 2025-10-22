"""Rate limiting for API endpoints.

Provides both in-memory and Redis-based rate limiting.
"""
from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from .config import Settings, get_settings


class InMemoryRateLimiter:
    """
    Simple in-memory token bucket rate limiter.

    Thread-safe for single-process deployments.
    For multi-process/distributed deployments, use RedisRateLimiter.
    """

    def __init__(self, qps: int):
        """
        Initialize rate limiter.

        Args:
            qps: Queries per second allowed
        """
        self.qps = qps
        self.buckets: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"tokens": float(qps), "last_update": time.time()}
        )
        self.lock = Lock()

    def check_rate_limit(self, key: str) -> None:
        """
        Check if request is within rate limit.

        Args:
            key: Identifier for rate limit bucket (e.g., IP address, API key)

        Raises:
            HTTPException: 429 if rate limit exceeded
        """
        with self.lock:
            now = time.time()
            bucket = self.buckets[key]

            # Refill tokens based on time elapsed
            elapsed = now - bucket["last_update"]
            bucket["tokens"] = min(self.qps, bucket["tokens"] + elapsed * self.qps)
            bucket["last_update"] = now

            # Check if token available
            if bucket["tokens"] >= 1:
                bucket["tokens"] -= 1
            else:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "code": "rate_limit_exceeded",
                        "message": f"Rate limit exceeded. Maximum {self.qps} requests per second.",
                    },
                )


class RedisRateLimiter:
    """
    Redis-based rate limiter for distributed deployments.

    Requires redis package and REDIS_URL configuration.
    """

    def __init__(self, qps: int, redis_url: str):
        """
        Initialize Redis rate limiter.

        Args:
            qps: Queries per second allowed
            redis_url: Redis connection URL
        """
        self.qps = qps
        self.redis_url = redis_url
        self._redis = None

    @property
    def redis(self):
        """Lazy-load Redis client."""
        if self._redis is None:
            try:
                import redis

                self._redis = redis.from_url(self.redis_url, decode_responses=True)
            except ImportError as e:
                raise RuntimeError(
                    "Redis rate limiting requires 'redis' package. Install with: pip install redis"
                ) from e
        return self._redis

    def check_rate_limit(self, key: str) -> None:
        """
        Check if request is within rate limit using Redis with atomic Lua script.

        Args:
            key: Identifier for rate limit bucket

        Raises:
            HTTPException: 429 if rate limit exceeded
        """
        redis_key = f"rate_limit:{key}"
        now = time.time()

        # Lua script for atomic rate limiting
        # Returns -1 if rate limit exceeded, otherwise returns current count
        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local qps = tonumber(ARGV[2])
        local window_start = now - 1

        -- Remove old entries (older than 1 second)
        redis.call('zremrangebyscore', key, 0, window_start)

        -- Count current requests in window
        local count = redis.call('zcard', key)

        -- Check if limit exceeded
        if count >= qps then
            return -1
        end

        -- Add current request
        redis.call('zadd', key, now, tostring(now))

        -- Set expiry (2 seconds to ensure cleanup)
        redis.call('expire', key, 2)

        return count
        """

        try:
            result = self.redis.eval(lua_script, 1, redis_key, now, self.qps)

            if result == -1:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "code": "rate_limit_exceeded",
                        "message": f"Rate limit exceeded. Maximum {self.qps} requests per second.",
                    },
                )
        except HTTPException:
            # Re-raise rate limit exceeded (don't swallow it)
            raise
        except Exception as e:
            # If Redis connection fails, allow request (fail open)
            # Log error in production
            pass


# Global rate limiter instance
_rate_limiter: InMemoryRateLimiter | RedisRateLimiter | None = None


def get_rate_limiter(settings: Settings | None = None) -> InMemoryRateLimiter | RedisRateLimiter | None:
    """
    Get or create rate limiter instance.

    Args:
        settings: API settings (uses get_settings() if not provided)

    Returns:
        Rate limiter instance or None if rate limiting is disabled
    """
    global _rate_limiter

    if settings is None:
        settings = get_settings()

    if settings.RATE_LIMIT_QPS is None:
        return None

    if _rate_limiter is None:
        if settings.REDIS_URL:
            _rate_limiter = RedisRateLimiter(settings.RATE_LIMIT_QPS, settings.REDIS_URL)
        else:
            _rate_limiter = InMemoryRateLimiter(settings.RATE_LIMIT_QPS)

    return _rate_limiter


async def rate_limit_dependency(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """
    FastAPI dependency for rate limiting.

    Can be used with Depends() in route definitions.

    Args:
        request: FastAPI request
        settings: API settings

    Raises:
        HTTPException: 429 if rate limit exceeded

    Example:
        @router.post("/endpoint", dependencies=[Depends(rate_limit_dependency)])
        async def my_endpoint():
            ...
    """
    limiter = get_rate_limiter(settings)
    if limiter is None:
        return  # Rate limiting disabled

    # Use client IP as key (or could use API key, user ID, etc.)
    client_ip = request.client.host if request.client else "unknown"
    limiter.check_rate_limit(client_ip)
