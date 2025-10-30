"""Idempotency middleware for preventing duplicate requests.

This middleware uses Idempotency-Key headers and request body hashes to detect
and prevent duplicate requests. Duplicate requests return a 409 Conflict response.
"""

import hashlib
import time
from typing import Any, Dict, Optional, Tuple

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class IdempotencyStore:
    """In-memory store for idempotency keys and request hashes.

    Stores tuples of (request_hash, response_body_bytes, status_code, headers, timestamp)
    keyed by idempotency key.
    """

    def __init__(self, ttl_seconds: int = 86400):  # 24 hours default
        """Initialize the idempotency store.

        Args:
            ttl_seconds: Time-to-live for stored entries in seconds
        """
        self._store: Dict[str, Tuple[str, bytes, int, Dict[str, str], float]] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[Tuple[str, bytes, int, Dict[str, str]]]:
        """Get stored request hash and response metadata for a given idempotency key.

        Args:
            key: The idempotency key

        Returns:
            Tuple of (request_hash, response_body_bytes, status_code, headers) if found
            and not expired, None otherwise
        """
        if key not in self._store:
            return None

        request_hash, response_body, status_code, headers, timestamp = self._store[key]

        # Check if expired
        if time.time() - timestamp > self._ttl:
            del self._store[key]
            return None

        return (request_hash, response_body, status_code, headers)

    def set(
        self,
        key: str,
        request_hash: str,
        response_body: bytes,
        status_code: int,
        headers: Dict[str, str],
    ) -> None:
        """Store an idempotency key with its request hash and response metadata.

        Args:
            key: The idempotency key
            request_hash: Hash of the request body
            response_body: The response body bytes to return for duplicate requests
            status_code: HTTP status code of the original response
            headers: Headers dict from the original response
        """
        self._store[key] = (request_hash, response_body, status_code, headers, time.time())

    def cleanup_expired(self) -> None:
        """Remove expired entries from the store."""
        current_time = time.time()
        expired_keys = [
            key
            for key, (_, _, _, _, timestamp) in self._store.items()
            if current_time - timestamp > self._ttl
        ]
        for key in expired_keys:
            del self._store[key]


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware to handle idempotent requests.

    This middleware:
    1. Checks for Idempotency-Key header in POST requests
    2. Hashes the request body
    3. Compares with stored requests to detect duplicates
    4. Returns 409 Conflict for duplicate requests with different bodies
    5. Returns cached response for exact duplicate requests
    """

    def __init__(self, app, store: Optional[IdempotencyStore] = None):
        """Initialize the idempotency middleware.

        Args:
            app: The FastAPI application
            store: Optional custom idempotency store, creates default if None
        """
        super().__init__(app)
        self._store = store or IdempotencyStore()

    async def dispatch(self, request: Request, call_next):
        """Process the request and apply idempotency logic.

        Args:
            request: The incoming request
            call_next: The next middleware or endpoint handler

        Returns:
            Response from the endpoint or cached/conflict response
        """
        # Only apply to POST requests
        if request.method != "POST":
            return await call_next(request)

        # Check for Idempotency-Key header
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            # No idempotency key, process normally
            return await call_next(request)

        # Read and hash the request body
        body = await request.body()
        request_hash = hashlib.sha256(body).hexdigest()

        # Check if we've seen this idempotency key before
        stored = self._store.get(idempotency_key)
        if stored:
            stored_hash, stored_body, stored_status, stored_headers = stored

            if stored_hash != request_hash:
                # Same key, different body - conflict
                return JSONResponse(
                    status_code=409,
                    content={
                        "code": "conflict",
                        "message": "Idempotency key already used with different request body"
                    }
                )

            # Exact duplicate - return cached response with original status code and headers
            # Add X-Idempotency-Replay header to indicate this is a cached response
            replay_headers = dict(stored_headers)
            replay_headers["X-Idempotency-Replay"] = "true"

            return Response(
                content=stored_body,
                status_code=stored_status,
                headers=replay_headers,
                media_type=stored_headers.get("content-type"),
            )

        # Process the request normally
        # We need to reconstruct the request with the body we already read
        async def receive():
            return {"type": "http.request", "body": body}

        request._receive = receive

        response = await call_next(request)

        # Store successful responses (2xx status codes)
        if 200 <= response.status_code < 300:
            # Read response body to cache it
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk

            # Store in idempotency cache with status code and headers
            # Store bytes directly without decoding to support binary responses
            self._store.set(
                idempotency_key,
                request_hash,
                response_body,
                response.status_code,
                dict(response.headers),
            )

            # Return response with reconstructed body
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )

        return response

    def cleanup_expired(self) -> None:
        """Manually trigger cleanup of expired idempotency entries."""
        self._store.cleanup_expired()
