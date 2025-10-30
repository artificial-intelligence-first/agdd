"""Idempotency middleware for preventing duplicate requests.

This middleware uses Idempotency-Key headers and request body hashes to detect
and prevent duplicate requests. Duplicate requests return a 409 Conflict response.
"""

import asyncio
import hashlib
import json
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
        # Track locks per idempotency key to prevent concurrent execution
        self._locks: Dict[str, asyncio.Lock] = {}
        # Lock to synchronize access to _locks dictionary
        self._locks_lock = asyncio.Lock()
        # Counter for periodic lock cleanup to prevent memory leaks
        self._request_count = 0
        self._cleanup_interval = 1000  # Clean up locks every N requests

    async def dispatch(self, request: Request, call_next):
        """Process the request and apply idempotency logic.

        Args:
            request: The incoming request
            call_next: The next middleware or endpoint handler

        Returns:
            Response from the endpoint or cached/conflict response
        """
        # Periodic cleanup to prevent lock memory leaks
        self._request_count += 1
        if self._request_count % self._cleanup_interval == 0:
            # Clean up expired store entries and stale locks
            self._store.cleanup_expired()
            await self._cleanup_locks()

        # Only apply to POST requests
        if request.method != "POST":
            return await call_next(request)

        # Read and hash the request body
        body = await request.body()
        request_hash = hashlib.sha256(body).hexdigest()

        # Check for Idempotency-Key in header (takes precedence) or in request body
        idempotency_key = request.headers.get("Idempotency-Key")

        if not idempotency_key:
            # Try to extract idempotency_key from JSON body
            try:
                body_json = json.loads(body.decode("utf-8"))
                if isinstance(body_json, dict):
                    idempotency_key = body_json.get("idempotency_key")
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                # Not JSON or can't decode - no idempotency key in body
                pass

        if not idempotency_key:
            # No idempotency key in header or body, process normally
            return await call_next(request)

        # Get or create a lock for this idempotency key to prevent concurrent execution
        async with self._locks_lock:
            if idempotency_key not in self._locks:
                self._locks[idempotency_key] = asyncio.Lock()
            key_lock = self._locks[idempotency_key]

        # Acquire the key-specific lock to ensure only one request with this key executes
        async with key_lock:
            # Double-check if the response is now in the store
            # (another request may have completed while we waited for the lock)
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
                # Note: We do NOT re-run background tasks for replayed responses,
                # as they already executed with the original request
                replay_headers = dict(stored_headers)
                replay_headers["X-Idempotency-Replay"] = "true"

                return Response(
                    content=stored_body,
                    status_code=stored_status,
                    headers=replay_headers,
                    media_type=stored_headers.get("content-type"),
                    # background=None by default - tasks already ran with original request
                )

            # Process the request normally
            # We need to reconstruct the request with the body we already read
            async def receive():
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": False,  # We've already read the entire body
                }

            request._receive = receive

            response = await call_next(request)

            # Store successful responses (2xx status codes)
            if 200 <= response.status_code < 300:
                # Check if this is a streaming response
                # Streaming responses typically lack Content-Length or have streaming media types
                is_streaming = self._is_streaming_response(response)

                if is_streaming:
                    # Don't cache streaming responses - pass through directly
                    # Streaming responses (SSE, websockets, large file downloads) are typically
                    # not idempotent and should not be buffered in memory
                    return response

                # Read response body to cache it (only for non-streaming responses)
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

                # Return response with reconstructed body and preserved background tasks
                return Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                    background=response.background,  # Preserve background tasks
                )

            # Non-2xx responses are not cached, return as-is
            return response

    def _is_streaming_response(self, response: Response) -> bool:
        """
        Detect if a response is a streaming response that should not be cached.

        Streaming responses are identified by:
        - Lack of Content-Length header
        - Media types like text/event-stream (Server-Sent Events)
        - Transfer-Encoding: chunked

        Args:
            response: The response to check

        Returns:
            True if the response is streaming and should not be cached
        """
        # Check for SSE or other streaming media types
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type or "application/x-ndjson" in content_type:
            return True

        # Check if Content-Length is missing (typical for streaming)
        # Presence of Content-Length usually indicates a complete, non-streaming response
        has_content_length = "content-length" in response.headers

        # Check for chunked transfer encoding
        transfer_encoding = response.headers.get("transfer-encoding", "")
        is_chunked = "chunked" in transfer_encoding.lower()

        # If no content-length and chunked encoding, it's likely streaming
        if not has_content_length and is_chunked:
            return True

        # If no content-length at all, be conservative and treat as streaming
        # to avoid buffering potentially large responses
        if not has_content_length:
            return True

        return False

    def cleanup_expired(self) -> None:
        """Manually trigger cleanup of expired idempotency entries."""
        self._store.cleanup_expired()

    async def _cleanup_locks(self) -> None:
        """Clean up locks for keys that are no longer in the store.

        This prevents memory leaks by removing lock objects for idempotency keys
        that have expired from the store. Only removes locks that are not currently
        being held to avoid interfering with in-flight requests.
        """
        async with self._locks_lock:
            # Find keys that exist in locks but not in store
            store_keys = set(self._store._store.keys())
            lock_keys = set(self._locks.keys())
            stale_keys = lock_keys - store_keys

            # Remove locks that are not currently held
            for key in stale_keys:
                lock = self._locks.get(key)
                if lock and not lock.locked():
                    del self._locks[key]
