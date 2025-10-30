"""Authentication and security utilities."""

from __future__ import annotations

import hashlib
import hmac

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
