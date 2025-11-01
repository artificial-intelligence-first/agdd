"""Authentication and security utilities."""

from __future__ import annotations

import hashlib
import hmac
from typing import Awaitable, Callable

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


async def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Verify API key from Authorization header or x-api-key header.

    Raises HTTPException 401 if API_KEY is configured but credentials are invalid.
    No-op if API_KEY is not configured (development mode).
    """
    if settings.API_KEY is None:
        return  # Authentication disabled

    token = None
    if credentials is not None:
        token = credentials.credentials
    elif x_api_key is not None:
        token = x_api_key

    if token != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Invalid API key"},
        )


def verify_github_signature(secret: str, signature_header: str | None, raw_body: bytes) -> bool:
    """
    Verify GitHub webhook signature using HMAC SHA-256.

    Args:
        secret: GitHub webhook secret
        signature_header: Value of X-Hub-Signature-256 header
        raw_body: Raw request body bytes

    Returns:
        True if signature is valid, False otherwise
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected_sig = signature_header[7:]  # Remove "sha256=" prefix
    computed_sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    return hmac.compare_digest(expected_sig, computed_sig)


# RBAC Scope-based authorization (added for WS-09)


def get_scopes_for_key(api_key: str) -> list[str]:
    """
    Get the list of scopes/permissions for a given API key.

    This is a mock implementation that returns all available scopes.
    In a production system, this would query a database or configuration
    to determine the actual scopes assigned to each API key.

    Args:
        api_key: The API key to look up scopes for

    Returns:
        List of scope strings (e.g., ["agents:run", "runs:read"])
    """
    # Mock implementation: return all scopes for now
    # TODO: Replace with actual scope lookup from database/config
    return [
        "agents:run",
        "agents:read",
        "runs:read",
        "runs:logs",
        "approvals:read",
        "approvals:write",
    ]


def require_scope(required_scopes: list[str]) -> Callable[..., Awaitable[str]]:
    """
    Create a FastAPI dependency that enforces RBAC scope requirements.

    This function returns a dependency that verifies the API key has
    all required scopes before allowing access to an endpoint.

    Args:
        required_scopes: List of scope strings that must all be present

    Returns:
        FastAPI dependency function that checks scopes

    Raises:
        HTTPException: 403 Forbidden if any required scope is missing

    Example:
        @router.post("/agents/{slug}/run",
                     dependencies=[Depends(require_scope(["agents:run"]))])
        async def run_agent(...):
            ...
    """

    async def check_scope(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        x_api_key: str | None = Header(default=None),
        settings: Settings = Depends(get_settings),
    ) -> str:
        """Verify API key and check required scopes."""
        # First verify the API key exists and is valid
        if settings.API_KEY is None:
            # Authentication disabled in development mode
            # Return a mock key for scope checking
            api_key = "dev-mode-key"
        else:
            token = None
            if credentials is not None:
                token = credentials.credentials
            elif x_api_key is not None:
                token = x_api_key

            if token != settings.API_KEY:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"code": "unauthorized", "message": "Invalid API key"},
                )
            api_key = token

        # Check scopes
        user_scopes = get_scopes_for_key(api_key)
        missing_scopes = [scope for scope in required_scopes if scope not in user_scopes]

        if missing_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "insufficient_permissions",
                    "message": f"Missing required scopes: {', '.join(missing_scopes)}",
                    "required_scopes": required_scopes,
                    "missing_scopes": missing_scopes,
                },
            )

        return api_key

    return check_scope
