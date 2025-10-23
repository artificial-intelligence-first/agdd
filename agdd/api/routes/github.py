"""GitHub webhook API endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from agdd.integrations.github.webhook import (
    handle_issue_comment,
    handle_pull_request,
    handle_pull_request_review_comment,
)

logger = logging.getLogger(__name__)

from ..config import Settings, get_settings
from ..rate_limit import rate_limit_dependency
from ..security import verify_github_signature

router = APIRouter(tags=["github"])


@router.post(
    "/github/webhook",
    dependencies=[Depends(rate_limit_dependency)],
)
async def webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """
    GitHub webhook endpoint.

    Receives webhook events from GitHub, verifies signature,
    and dispatches to appropriate handlers.

    Supported events:
    - issue_comment: Comments on issues
    - pull_request_review_comment: Comments on PR reviews
    - pull_request: PR open/edit/sync

    Args:
        request: FastAPI request
        x_github_event: Event type header
        x_hub_signature_256: HMAC signature header
        settings: API settings

    Returns:
        Status response

    Raises:
        HTTPException: 401 if signature verification fails
    """
    # Read raw body for signature verification
    raw_body = await request.body()

    # Verify signature if secret is configured
    if settings.GITHUB_WEBHOOK_SECRET:
        if not verify_github_signature(
            settings.GITHUB_WEBHOOK_SECRET,
            x_hub_signature_256,
            raw_body,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "invalid_signature",
                    "message": "Webhook signature verification failed",
                },
            )

    # Parse JSON payload
    try:
        payload: dict[str, Any] = await request.json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_payload", "message": f"Failed to parse JSON: {e}"},
        ) from e

    # Dispatch based on event type
    if x_github_event == "issue_comment":
        await handle_issue_comment(payload, settings)
    elif x_github_event == "pull_request_review_comment":
        await handle_pull_request_review_comment(payload, settings)
    elif x_github_event == "pull_request":
        await handle_pull_request(payload, settings)
    else:
        # Silently ignore unsupported event types
        logger.debug(f"Ignoring unsupported GitHub event type: {x_github_event}")

    return {"status": "ok"}


@router.get(
    "/github/health",
    dependencies=[Depends(rate_limit_dependency)],
)
async def health() -> dict[str, str]:
    """
    Health check endpoint for GitHub integration.

    Returns:
        Health status
    """
    return {"status": "healthy", "integration": "github"}
