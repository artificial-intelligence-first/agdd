"""
Approval Gate for tool execution governance.

Implements approval-as-a-policy workflow for controlling agent actions
that require human oversight. This module provides the core logic for
evaluating tool permissions, creating approval tickets, and managing
the approval lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from agdd.core.permissions import ApprovalTicket, ToolPermission

logger = logging.getLogger(__name__)


class ApprovalGateError(Exception):
    """Base exception for approval gate errors."""

    pass


class ApprovalTimeoutError(ApprovalGateError):
    """Approval request timed out."""

    pass


class ApprovalDeniedError(ApprovalGateError):
    """Approval request was denied."""

    pass


class ApprovalGate:
    """
    Approval gate for tool execution governance.

    Evaluates tool permissions, creates approval tickets, and manages
    the approval lifecycle. Integrates with permission evaluator and
    approval storage backend.
    """

    def __init__(
        self,
        permission_evaluator: Any,  # PermissionEvaluator instance
        ticket_store: Optional[Any] = None,  # Storage backend for tickets
        default_timeout_minutes: int = 30,
    ):
        """
        Initialize approval gate.

        Args:
            permission_evaluator: Permission evaluator instance
            ticket_store: Storage backend for approval tickets (optional)
            default_timeout_minutes: Default approval timeout
        """
        self.permission_evaluator = permission_evaluator
        self.ticket_store = ticket_store
        self.default_timeout_minutes = default_timeout_minutes

        # In-memory ticket storage (fallback if no ticket_store provided)
        self._tickets: Dict[str, ApprovalTicket] = {}

    def evaluate(
        self,
        tool_name: str,
        context: Dict[str, Any],
    ) -> ToolPermission:
        """
        Evaluate permission for a tool execution.

        Args:
            tool_name: Name of the tool to execute
            context: Execution context (agent, args, etc.)

        Returns:
            ToolPermission level (ALWAYS, REQUIRE_APPROVAL, NEVER)
        """
        logger.debug(f"Evaluating permission for tool: {tool_name}")

        # Delegate to permission evaluator
        permission = self.permission_evaluator.evaluate(tool_name, context)

        logger.info(
            f"Tool {tool_name} permission: {permission.value} "
            f"(agent={context.get('agent_slug')}, run={context.get('run_id')})"
        )

        return permission

    def create_ticket(
        self,
        run_id: str,
        agent_slug: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        timeout_minutes: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApprovalTicket:
        """
        Create an approval ticket for a pending tool execution.

        Args:
            run_id: Run identifier
            agent_slug: Agent requesting approval
            tool_name: Tool name
            tool_args: Tool arguments
            timeout_minutes: Approval timeout (default: from config)
            metadata: Optional metadata

        Returns:
            ApprovalTicket instance
        """
        from uuid import uuid4

        timeout_minutes = timeout_minutes or self.default_timeout_minutes

        ticket = ApprovalTicket(
            ticket_id=str(uuid4()),
            run_id=run_id,
            agent_slug=agent_slug,
            tool_name=tool_name,
            tool_args=tool_args,
            requested_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=timeout_minutes),
            status="pending",
        )

        # Store ticket
        self._tickets[ticket.ticket_id] = ticket

        if self.ticket_store:
            # Placeholder: Store in persistent backend
            logger.debug(f"Storing ticket {ticket.ticket_id} in persistent store")

        logger.info(
            f"Created approval ticket {ticket.ticket_id} for {tool_name} "
            f"(expires in {timeout_minutes} minutes)"
        )

        return ticket

    async def wait_for_decision(
        self,
        ticket: ApprovalTicket,
        poll_interval_seconds: float = 5.0,
    ) -> ApprovalTicket:
        """
        Wait for approval decision (polling implementation).

        This is a polling-based implementation. For production, consider
        using SSE (Server-Sent Events) or WebSocket for real-time updates.

        Args:
            ticket: Approval ticket
            poll_interval_seconds: Polling interval

        Returns:
            Updated ApprovalTicket with decision

        Raises:
            ApprovalTimeoutError: If ticket expires before decision
            ApprovalDeniedError: If approval is denied
        """
        logger.info(f"Waiting for approval decision on ticket {ticket.ticket_id}")

        while True:
            # Check if ticket has expired
            if datetime.utcnow() >= ticket.expires_at:
                logger.warning(f"Approval ticket {ticket.ticket_id} expired")
                ticket.status = "expired"
                raise ApprovalTimeoutError(
                    f"Approval request timed out for {ticket.tool_name}"
                )

            # Refresh ticket from store
            current_ticket = self.get_ticket(ticket.ticket_id)
            if current_ticket is None:
                raise ApprovalGateError(
                    f"Approval ticket {ticket.ticket_id} not found"
                )

            # Check if decision has been made
            if current_ticket.status == "approved":
                logger.info(
                    f"Approval ticket {ticket.ticket_id} approved "
                    f"by {current_ticket.resolved_by}"
                )
                return current_ticket

            elif current_ticket.status == "denied":
                logger.warning(
                    f"Approval ticket {ticket.ticket_id} denied "
                    f"by {current_ticket.resolved_by}"
                )
                raise ApprovalDeniedError(
                    f"Approval denied for {ticket.tool_name}"
                )

            # Still pending - wait and poll again
            await asyncio.sleep(poll_interval_seconds)

    def get_ticket(self, ticket_id: str) -> Optional[ApprovalTicket]:
        """
        Get an approval ticket by ID.

        Args:
            ticket_id: Ticket identifier

        Returns:
            ApprovalTicket or None if not found
        """
        if self.ticket_store:
            # Placeholder: Retrieve from persistent backend
            pass

        return self._tickets.get(ticket_id)

    def approve_ticket(
        self,
        ticket_id: str,
        approved_by: str,
        response: Optional[Dict[str, Any]] = None,
    ) -> ApprovalTicket:
        """
        Approve an approval ticket.

        Args:
            ticket_id: Ticket identifier
            approved_by: User who approved
            response: Optional response data

        Returns:
            Updated ApprovalTicket

        Raises:
            ApprovalGateError: If ticket not found or already resolved
        """
        ticket = self.get_ticket(ticket_id)
        if ticket is None:
            raise ApprovalGateError(f"Approval ticket {ticket_id} not found")

        if ticket.status != "pending":
            raise ApprovalGateError(
                f"Approval ticket {ticket_id} already {ticket.status}"
            )

        # Update ticket
        ticket.status = "approved"
        ticket.resolved_at = datetime.utcnow()
        ticket.resolved_by = approved_by
        ticket.response = response or {}

        # Store updated ticket
        self._tickets[ticket_id] = ticket

        if self.ticket_store:
            # Placeholder: Update in persistent backend
            logger.debug(f"Updating ticket {ticket_id} in persistent store")

        logger.info(f"Approved ticket {ticket_id} by {approved_by}")

        return ticket

    def deny_ticket(
        self,
        ticket_id: str,
        denied_by: str,
        reason: Optional[str] = None,
    ) -> ApprovalTicket:
        """
        Deny an approval ticket.

        Args:
            ticket_id: Ticket identifier
            denied_by: User who denied
            reason: Optional reason for denial

        Returns:
            Updated ApprovalTicket

        Raises:
            ApprovalGateError: If ticket not found or already resolved
        """
        ticket = self.get_ticket(ticket_id)
        if ticket is None:
            raise ApprovalGateError(f"Approval ticket {ticket_id} not found")

        if ticket.status != "pending":
            raise ApprovalGateError(
                f"Approval ticket {ticket_id} already {ticket.status}"
            )

        # Update ticket
        ticket.status = "denied"
        ticket.resolved_at = datetime.utcnow()
        ticket.resolved_by = denied_by
        ticket.response = {"reason": reason} if reason else {}

        # Store updated ticket
        self._tickets[ticket_id] = ticket

        if self.ticket_store:
            # Placeholder: Update in persistent backend
            logger.debug(f"Updating ticket {ticket_id} in persistent store")

        logger.info(f"Denied ticket {ticket_id} by {denied_by}: {reason}")

        return ticket

    def list_pending_tickets(
        self,
        run_id: Optional[str] = None,
        agent_slug: Optional[str] = None,
    ) -> list[ApprovalTicket]:
        """
        List pending approval tickets.

        Args:
            run_id: Filter by run ID (optional)
            agent_slug: Filter by agent slug (optional)

        Returns:
            List of pending ApprovalTickets
        """
        tickets = []

        for ticket in self._tickets.values():
            # Filter by status
            if ticket.status != "pending":
                continue

            # Filter by run_id
            if run_id and ticket.run_id != run_id:
                continue

            # Filter by agent_slug
            if agent_slug and ticket.agent_slug != agent_slug:
                continue

            tickets.append(ticket)

        # Sort by requested_at (oldest first)
        tickets.sort(key=lambda t: t.requested_at)

        return tickets

    def expire_old_tickets(self) -> int:
        """
        Expire old tickets that have passed their TTL.

        Returns:
            Number of tickets expired
        """
        now = datetime.utcnow()
        expired_count = 0

        for ticket_id, ticket in list(self._tickets.items()):
            if ticket.status == "pending" and now >= ticket.expires_at:
                ticket.status = "expired"
                self._tickets[ticket_id] = ticket
                expired_count += 1

                logger.info(f"Expired ticket {ticket_id}")

        if expired_count > 0:
            logger.info(f"Expired {expired_count} approval tickets")

        return expired_count

    async def execute_with_approval(
        self,
        run_id: str,
        agent_slug: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_fn: Any,  # Callable to execute if approved
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Execute a tool with approval gate check.

        High-level method that combines permission evaluation, ticket
        creation, approval waiting, and tool execution.

        Args:
            run_id: Run identifier
            agent_slug: Agent slug
            tool_name: Tool name
            tool_args: Tool arguments
            tool_fn: Tool function to execute if approved
            context: Optional execution context

        Returns:
            Tool execution result

        Raises:
            ApprovalDeniedError: If approval is denied
            ApprovalTimeoutError: If approval times out
        """
        # Build context
        ctx = context or {}
        ctx.update({
            "agent_slug": agent_slug,
            "run_id": run_id,
            "tool_name": tool_name,
            "tool_args": tool_args,
        })

        # Evaluate permission
        permission = self.evaluate(tool_name, ctx)

        if permission == ToolPermission.NEVER:
            raise ApprovalDeniedError(
                f"Tool {tool_name} is not allowed by policy"
            )

        if permission == ToolPermission.ALWAYS:
            logger.info(f"Tool {tool_name} allowed without approval")
            return await tool_fn(**tool_args)

        if permission == ToolPermission.REQUIRE_APPROVAL:
            # Create approval ticket
            ticket = self.create_ticket(
                run_id=run_id,
                agent_slug=agent_slug,
                tool_name=tool_name,
                tool_args=tool_args,
            )

            # Wait for decision
            try:
                await self.wait_for_decision(ticket)
                logger.info(f"Executing {tool_name} after approval")
                return await tool_fn(**tool_args)

            except (ApprovalTimeoutError, ApprovalDeniedError):
                # Re-raise approval errors
                raise

        raise ApprovalGateError(f"Unknown permission level: {permission}")
