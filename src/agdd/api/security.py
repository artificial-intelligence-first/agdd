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


def require_scope(*required_scopes: str):
    """
    Create a dependency that verifies the API key has required scopes.

    This is a basic RBAC scope checking mechanism. Currently, it verifies
    authentication (via require_api_key) and can be extended to check
    specific scopes against user/key metadata.

    Args:
        *required_scopes: One or more scope strings that are required

    Returns:
        Async dependency function that can be used with Depends()

    Example:
        @router.post("/admin/users", dependencies=[Depends(require_scope("admin:write"))])
        async def create_user(...):
            ...
    """
    async def _check_scopes(
        _: None = Depends(require_api_key),
        settings: Settings = Depends(get_settings),
    ) -> None:
        """
        Verify that the authenticated request has the required scopes.

        For now, this is a placeholder that ensures authentication.
        Future implementations can check scopes against API key metadata,
        user permissions stored in a database, or JWT claims.

        Args:
            _: Authentication check via require_api_key
            settings: API settings

        Raises:
            HTTPException: 403 if required scopes are not present
        """
        # TODO: Implement actual scope checking when scope metadata is available
        # For now, if we've passed require_api_key, we allow all scopes
        # This can be extended to check against:
        # - API key metadata in a database
        # - JWT claims
        # - User permissions table
        #
        # Example future implementation:
        # user_scopes = get_user_scopes_from_token(token)
        # missing_scopes = set(required_scopes) - set(user_scopes)
        # if missing_scopes:
        #     raise HTTPException(
        #         status_code=status.HTTP_403_FORBIDDEN,
        #         detail={
        #             "code": "forbidden",
        #             "message": f"Missing required scopes: {', '.join(missing_scopes)}"
        #         }
        #     )
        pass

    return _check_scopes
