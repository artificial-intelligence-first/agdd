"""
A2A Communication - JSON-RPC 2.0 message handling.

Provides JSON-RPC 2.0 compliant request/response handling for agent-to-agent
communication, including method dispatching, error handling, and extension
hooks for authentication and authorization.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from .types import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
)


class MessageHandler:
    """
    JSON-RPC 2.0 message handler.

    Manages method registration and dispatching for incoming JSON-RPC requests.
    """

    def __init__(self) -> None:
        """Initialize message handler with empty method registry."""
        self._methods: dict[str, Callable[..., Any]] = {}

    def register_method(
        self,
        name: str,
        handler: Callable[..., Any],
    ) -> None:
        """
        Register a method handler.

        Args:
            name: Method name
            handler: Callable that handles the method (receives params as kwargs)

        Raises:
            ValueError: If method is already registered
        """
        if name in self._methods:
            raise ValueError(f"Method '{name}' is already registered")
        self._methods[name] = handler

    def unregister_method(self, name: str) -> None:
        """
        Unregister a method handler.

        Args:
            name: Method name to unregister
        """
        self._methods.pop(name, None)

    def has_method(self, name: str) -> bool:
        """
        Check if a method is registered.

        Args:
            name: Method name

        Returns:
            True if method is registered, False otherwise
        """
        return name in self._methods

    def handle_request(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """
        Handle a JSON-RPC request.

        Args:
            request: JSON-RPC request to handle

        Returns:
            JSON-RPC response
        """
        # Check if method exists
        if not self.has_method(request.method):
            return JsonRpcResponse(
                id=request.id,
                error=JsonRpcError(
                    code=METHOD_NOT_FOUND,
                    message=f"Method not found: {request.method}",
                ),
            )

        # Get method handler
        handler = self._methods[request.method]

        try:
            # Call handler with params
            if request.params is None:
                result = handler()
            elif isinstance(request.params, dict):
                result = handler(**request.params)
            elif isinstance(request.params, list):
                result = handler(*request.params)
            else:
                return JsonRpcResponse(
                    id=request.id,
                    error=JsonRpcError(
                        code=INVALID_PARAMS,
                        message="Invalid params: must be object or array",
                    ),
                )

            return JsonRpcResponse(id=request.id, result=result)

        except TypeError as e:
            # Parameter mismatch
            return JsonRpcResponse(
                id=request.id,
                error=JsonRpcError(
                    code=INVALID_PARAMS,
                    message=f"Invalid params: {e}",
                ),
            )
        except Exception as e:
            # Internal error
            return JsonRpcResponse(
                id=request.id,
                error=JsonRpcError(
                    code=INTERNAL_ERROR,
                    message=f"Internal error: {e}",
                    data={"exception_type": type(e).__name__},
                ),
            )


class A2AClient:
    """
    Client for sending JSON-RPC 2.0 requests to agents.

    Provides a high-level interface for making RPC calls to other agents.
    """

    def __init__(self) -> None:
        """Initialize A2A client."""
        self._request_id_counter = 0

    def _generate_request_id(self) -> str:
        """
        Generate unique request ID.

        Returns:
            Unique request identifier
        """
        self._request_id_counter += 1
        return f"{uuid.uuid4().hex[:8]}-{self._request_id_counter}"

    def create_request(
        self,
        method: str,
        params: dict[str, Any] | list[Any] | None = None,
        request_id: str | int | None = None,
        meta: dict[str, Any] | None = None,
    ) -> JsonRpcRequest:
        """
        Create a JSON-RPC request.

        Args:
            method: Method name to invoke
            params: Method parameters (dict or list)
            request_id: Optional request ID (auto-generated if None)
            meta: Optional metadata for extensions (signatures, auth)

        Returns:
            JSON-RPC request object
        """
        if request_id is None:
            request_id = self._generate_request_id()

        return JsonRpcRequest(
            method=method,
            params=params,
            id=request_id,
            meta=meta,
        )

    def create_notification(
        self,
        method: str,
        params: dict[str, Any] | list[Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> JsonRpcRequest:
        """
        Create a JSON-RPC notification (no response expected).

        Args:
            method: Method name to invoke
            params: Method parameters (dict or list)
            meta: Optional metadata for extensions

        Returns:
            JSON-RPC notification (request with id=None)
        """
        return JsonRpcRequest(
            method=method,
            params=params,
            id=None,
            meta=meta,
        )

    def parse_response(self, response_data: dict[str, Any]) -> JsonRpcResponse:
        """
        Parse a JSON-RPC response from raw data.

        Args:
            response_data: Raw response data (dict)

        Returns:
            Parsed JSON-RPC response

        Raises:
            ValidationError: If response is invalid
        """
        return JsonRpcResponse.model_validate(response_data)


class A2AServer:
    """
    Server for handling incoming JSON-RPC 2.0 requests.

    Combines MessageHandler with request validation and error handling.
    """

    def __init__(self) -> None:
        """Initialize A2A server."""
        self._handler = MessageHandler()

    def register_method(
        self,
        name: str,
        handler: Callable[..., Any],
    ) -> None:
        """
        Register a method handler.

        Args:
            name: Method name
            handler: Callable that handles the method

        Raises:
            ValueError: If method is already registered
        """
        self._handler.register_method(name, handler)

    def unregister_method(self, name: str) -> None:
        """
        Unregister a method handler.

        Args:
            name: Method name to unregister
        """
        self._handler.unregister_method(name)

    def handle_request_dict(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """
        Handle a JSON-RPC request from raw data.

        Args:
            request_data: Raw request data (dict)

        Returns:
            Response data (dict)
        """
        try:
            # Parse request
            request = JsonRpcRequest.model_validate(request_data)

            # Handle request
            response = self._handler.handle_request(request)

            return response.model_dump(exclude_none=True)

        except Exception as e:
            # Invalid request
            return JsonRpcResponse(
                id=None,
                error=JsonRpcError(
                    code=INVALID_REQUEST,
                    message=f"Invalid request: {e}",
                ),
            ).model_dump(exclude_none=True)

    def handle_request(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """
        Handle a JSON-RPC request object.

        Args:
            request: JSON-RPC request

        Returns:
            JSON-RPC response
        """
        return self._handler.handle_request(request)


# Extension point: Middleware for authentication/authorization


class RequestMiddleware:
    """
    Base class for request middleware.

    Middleware can intercept requests before they're processed and responses
    before they're returned, enabling authentication, authorization, logging,
    rate limiting, etc.
    """

    def before_request(self, request: JsonRpcRequest) -> JsonRpcRequest | JsonRpcResponse:
        """
        Process request before handling.

        Args:
            request: Incoming request

        Returns:
            Modified request to continue processing, or response to short-circuit
        """
        return request

    def after_request(
        self,
        request: JsonRpcRequest,
        response: JsonRpcResponse,
    ) -> JsonRpcResponse:
        """
        Process response before returning.

        Args:
            request: Original request
            response: Generated response

        Returns:
            Modified response
        """
        return response
