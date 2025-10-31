"""Approval API endpoints for v0.2 approval-as-a-policy feature."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agdd.core.permissions import ApprovalTicket
from agdd.governance.approval_gate import ApprovalGate

from ..config import Settings, get_settings
from ..rate_limit import rate_limit_dependency
from ..security import require_scope

router = APIRouter(tags=["approvals"])


# Request/Response Models
class ApprovalDecisionRequest(BaseModel):
    """Request to approve or deny an approval ticket."""

    action: Literal["approve", "deny"] = Field(
        ..., description="Action to take on the approval ticket"
    )
    resolved_by: str = Field(..., description="User or system that resolved the approval")
    reason: Optional[str] = Field(None, description="Reason for denial (for deny action)")
    response: Optional[dict] = Field(None, description="Additional response data (for approve action)")


class ApprovalTicketResponse(BaseModel):
    """Response containing approval ticket details."""

    ticket_id: str
    run_id: str
    agent_slug: str
    tool_name: str
    tool_args: dict
    status: Literal["pending", "approved", "denied", "expired"]
    requested_at: str
    expires_at: str
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    response: Optional[dict] = None

    @classmethod
    def from_ticket(cls, ticket: ApprovalTicket) -> ApprovalTicketResponse:
        """Convert ApprovalTicket to API response model."""
        return cls(
            ticket_id=ticket.ticket_id,
            run_id=ticket.run_id,
            agent_slug=ticket.agent_slug,
            tool_name=ticket.tool_name,
            tool_args=ticket.tool_args,
            status=ticket.status,
            requested_at=ticket.requested_at.isoformat(),
            expires_at=ticket.expires_at.isoformat(),
            resolved_at=ticket.resolved_at.isoformat() if ticket.resolved_at else None,
            resolved_by=ticket.resolved_by,
            response=ticket.response,
        )


class ApprovalListResponse(BaseModel):
    """Response containing list of approval tickets."""

    tickets: list[ApprovalTicketResponse]
    count: int


# Global approval gate instance (will be initialized per request in production)
# For now, using module-level singleton with in-memory storage
_approval_gate: Optional[ApprovalGate] = None


def get_approval_gate(settings: Settings = Depends(get_settings)) -> ApprovalGate:
    """
    Get or create approval gate instance.

    In production, this should be replaced with proper dependency injection
    that includes persistent storage backend.
    """
    global _approval_gate

    if not settings.APPROVALS_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "feature_disabled",
                "message": "Approval-as-a-policy feature is not enabled",
            },
        )

    if _approval_gate is None:
        # Import here to avoid circular dependency
        from agdd.governance.permission_evaluator import PermissionEvaluator

        # Create permission evaluator (loads policies from catalog)
        permission_evaluator = PermissionEvaluator()

        # Create approval gate with in-memory storage
        _approval_gate = ApprovalGate(
            permission_evaluator=permission_evaluator,
            ticket_store=None,  # TODO: Wire up persistent storage
            default_timeout_minutes=settings.APPROVAL_TTL_MIN,
        )

    return _approval_gate


@router.get(
    "/runs/{run_id}/approvals",
    response_model=ApprovalListResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def list_approvals(
    run_id: str,
    _: str = Depends(require_scope(["approvals:read"])),
    approval_gate: ApprovalGate = Depends(get_approval_gate),
) -> ApprovalListResponse:
    """
    List all approval tickets for a run.

    Args:
        run_id: Run identifier

    Returns:
        List of approval tickets

    Raises:
        HTTPException: 503 if approvals feature is disabled
    """
    tickets = approval_gate.list_pending_tickets(run_id=run_id)

    return ApprovalListResponse(
        tickets=[ApprovalTicketResponse.from_ticket(t) for t in tickets],
        count=len(tickets),
    )


@router.get(
    "/runs/{run_id}/approvals/{approval_id}",
    response_model=ApprovalTicketResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def get_approval(
    run_id: str,
    approval_id: str,
    _: str = Depends(require_scope(["approvals:read"])),
    approval_gate: ApprovalGate = Depends(get_approval_gate),
) -> ApprovalTicketResponse:
    """
    Get approval ticket details.

    Args:
        run_id: Run identifier
        approval_id: Approval ticket ID

    Returns:
        Approval ticket details

    Raises:
        HTTPException: 404 if ticket not found, 503 if feature disabled
    """
    ticket = approval_gate.get_ticket(approval_id)

    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_found",
                "message": f"Approval ticket not found: {approval_id}",
            },
        )

    # Verify ticket belongs to the specified run
    if ticket.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_found",
                "message": f"Approval ticket not found for run: {run_id}",
            },
        )

    return ApprovalTicketResponse.from_ticket(ticket)


@router.post(
    "/runs/{run_id}/approvals/{approval_id}",
    response_model=ApprovalTicketResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def update_approval(
    run_id: str,
    approval_id: str,
    request: ApprovalDecisionRequest,
    _: str = Depends(require_scope(["approvals:write"])),
    approval_gate: ApprovalGate = Depends(get_approval_gate),
) -> ApprovalTicketResponse:
    """
    Approve or deny an approval ticket.

    Args:
        run_id: Run identifier
        approval_id: Approval ticket ID
        request: Approval decision request

    Returns:
        Updated approval ticket

    Raises:
        HTTPException: 404 if ticket not found, 400 if already resolved,
                      503 if feature disabled
    """
    ticket = approval_gate.get_ticket(approval_id)

    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_found",
                "message": f"Approval ticket not found: {approval_id}",
            },
        )

    # Verify ticket belongs to the specified run
    if ticket.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_found",
                "message": f"Approval ticket not found for run: {run_id}",
            },
        )

    # Check if ticket is still pending
    if ticket.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_request",
                "message": f"Approval ticket already {ticket.status}",
            },
        )

    # Execute decision
    try:
        if request.action == "approve":
            updated_ticket = approval_gate.approve_ticket(
                ticket_id=approval_id,
                approved_by=request.resolved_by,
                response=request.response,
            )
        elif request.action == "deny":
            updated_ticket = approval_gate.deny_ticket(
                ticket_id=approval_id,
                denied_by=request.resolved_by,
                reason=request.reason,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "invalid_request",
                    "message": f"Invalid action: {request.action}",
                },
            )

        return ApprovalTicketResponse.from_ticket(updated_ticket)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "internal_error",
                "message": f"Failed to update approval ticket: {str(e)}",
            },
        ) from e


@router.get(
    "/runs/{run_id}/approvals/{approval_id}/events",
    dependencies=[Depends(rate_limit_dependency)],
)
async def stream_approval_events(
    run_id: str,
    approval_id: str,
    _: str = Depends(require_scope(["approvals:read"])),
    approval_gate: ApprovalGate = Depends(get_approval_gate),
) -> StreamingResponse:
    """
    Stream approval ticket updates via Server-Sent Events (SSE).

    Clients can subscribe to this endpoint to receive real-time updates
    when an approval ticket status changes.

    Args:
        run_id: Run identifier
        approval_id: Approval ticket ID

    Returns:
        SSE stream with approval ticket updates

    Raises:
        HTTPException: 404 if ticket not found, 503 if feature disabled
    """
    # Verify ticket exists
    ticket = approval_gate.get_ticket(approval_id)

    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_found",
                "message": f"Approval ticket not found: {approval_id}",
            },
        )

    # Verify ticket belongs to the specified run
    if ticket.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "not_found",
                "message": f"Approval ticket not found for run: {run_id}",
            },
        )

    async def sse_stream() -> AsyncIterator[bytes]:
        """
        Generate SSE events for approval ticket updates.

        Emits events:
        - approval.required: Initial state (pending)
        - approval.updated: Status changed (approved/denied/expired)
        """
        import json

        # Send initial state
        current_ticket = approval_gate.get_ticket(approval_id)
        if current_ticket:
            event_data = ApprovalTicketResponse.from_ticket(current_ticket).model_dump()
            yield f"event: approval.required\n".encode("utf-8")
            yield f"data: {json.dumps(event_data)}\n\n".encode("utf-8")

        # Poll for updates
        last_status = current_ticket.status if current_ticket else None
        poll_interval = 2.0  # seconds

        while True:
            await asyncio.sleep(poll_interval)

            current_ticket = approval_gate.get_ticket(approval_id)
            if current_ticket is None:
                # Ticket was deleted
                break

            # Check if status changed
            if current_ticket.status != last_status:
                event_data = ApprovalTicketResponse.from_ticket(current_ticket).model_dump()
                yield f"event: approval.updated\n".encode("utf-8")
                yield f"data: {json.dumps(event_data)}\n\n".encode("utf-8")

                last_status = current_ticket.status

                # If resolved or expired, close stream
                if current_ticket.status in ("approved", "denied", "expired"):
                    break

    return StreamingResponse(sse_stream(), media_type="text/event-stream")
