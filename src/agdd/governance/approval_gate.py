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
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, Union, cast

from agdd.core.permissions import (
    ApprovalStatus,
    ApprovalTicket,
    ToolPermission,
    compute_args_hash,
    mask_tool_args,
)
from agdd.storage.models import ApprovalTicketRecord
from agdd.storage.serialization import json_safe

if TYPE_CHECKING:  # pragma: no cover - typing aid
    from agdd.storage.base import StorageBackend

logger = logging.getLogger(__name__)

class PermissionEvaluatorProtocol(Protocol):
    """Protocol describing the required permission evaluator interface."""

    def evaluate(self, tool_name: str, context: Dict[str, Any]) -> Union[ToolPermission, str]:
        ...


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
        permission_evaluator: PermissionEvaluatorProtocol,
        ticket_store: Optional["StorageBackend"] = None,  # Storage backend for tickets
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
        self._lock = asyncio.Lock()
        self._initialized_runs: set[str] = set()
        self._run_init_lock = asyncio.Lock()

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
        raw_permission = self.permission_evaluator.evaluate(tool_name, context)
        if isinstance(raw_permission, ToolPermission):
            permission = raw_permission
        elif isinstance(raw_permission, str):
            try:
                permission = ToolPermission(raw_permission)
            except ValueError as exc:
                raise ValueError(f"Unsupported permission value: {raw_permission}") from exc
        else:
            raise TypeError(
                f"Permission evaluator returned unsupported type {type(raw_permission)!r}"
            )

        logger.info(
            f"Tool {tool_name} permission: {permission.value} "
            f"(agent={context.get('agent_slug')}, run={context.get('run_id')})"
        )

        return permission

    async def create_ticket(
        self,
        run_id: str,
        agent_slug: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        step_id: Optional[str] = None,
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
            step_id: Optional execution step identifier
            timeout_minutes: Approval timeout (default: from config)
            metadata: Optional metadata

        Returns:
            ApprovalTicket instance
        """
        from uuid import uuid4

        timeout_minutes = timeout_minutes or self.default_timeout_minutes
        requested_at = datetime.now(UTC)
        expires_at = requested_at + timedelta(minutes=timeout_minutes)
        masked_args = mask_tool_args(tool_args)
        args_hash = compute_args_hash(tool_args)

        ticket = ApprovalTicket(
            ticket_id=str(uuid4()),
            run_id=run_id,
            agent_slug=agent_slug,
            tool_name=tool_name,
            tool_args=tool_args,
            args_hash=args_hash,
            requested_at=requested_at,
            expires_at=expires_at,
            status="pending",
            masked_args=masked_args,
            step_id=step_id,
            metadata=metadata or {},
        )

        async with self._lock:
            self._tickets[ticket.ticket_id] = ticket

        if self.ticket_store:
            await self._ensure_run_record(
                run_id=run_id,
                agent_slug=agent_slug,
                metadata=metadata,
            )
            record = self._ticket_to_record(ticket)
            try:
                await self.ticket_store.create_approval_ticket(record)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    "Failed to persist approval ticket %s: %s",
                    ticket.ticket_id,
                    exc,
                )
            else:
                await self._emit_event(
                    "approval.required",
                    ticket,
                    message=f"Approval required for tool {tool_name}",
                    extras={"timeout_minutes": timeout_minutes},
                )

        logger.info(
            f"Created approval ticket {ticket.ticket_id} for {tool_name} "
            f"(expires in {timeout_minutes} minutes)"
        )

        return ticket

    async def _ensure_run_record(
        self,
        run_id: str,
        agent_slug: str,
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        """Ensure a run row exists before persisting approval tickets."""
        if not run_id or self.ticket_store is None:
            return

        if run_id in self._initialized_runs:
            return

        async with self._run_init_lock:
            if run_id in self._initialized_runs:
                return

            backend = self.ticket_store

            try:
                existing = await backend.get_run(run_id)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.debug("Approval gate could not fetch run %s: %s", run_id, exc)
                existing = None

            if existing:
                self._initialized_runs.add(run_id)
                return

            parent_run_id = self._extract_parent_run_id(metadata)
            tags = self._extract_tags(metadata)

            try:
                await backend.create_run(
                    run_id=run_id,
                    agent_slug=agent_slug or "unknown",
                    parent_run_id=parent_run_id,
                    started_at=datetime.now(UTC),
                    status="running",
                    tags=tags,
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Approval gate could not create run %s: %s", run_id, exc)
            else:
                self._initialized_runs.add(run_id)

    def _extract_parent_run_id(self, metadata: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(metadata, dict):
            return None
        for key in ("parent_run_id", "parent", "parent_run"):
            value = metadata.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _extract_tags(self, metadata: Optional[Dict[str, Any]]) -> Optional[List[str]]:
        if not isinstance(metadata, dict):
            return None
        tags = metadata.get("tags")
        if isinstance(tags, list) and all(isinstance(tag, str) for tag in tags):
            return tags
        return None

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
            current_ticket = await self.get_ticket(ticket.ticket_id)
            if current_ticket is None:
                raise ApprovalGateError(
                    f"Approval ticket {ticket.ticket_id} not found"
                )

            # Check if ticket has expired
            if datetime.now(UTC) >= current_ticket.expires_at:
                logger.warning(f"Approval ticket {ticket.ticket_id} expired")
                await self._expire_ticket(current_ticket)
                raise ApprovalTimeoutError(
                    f"Approval request timed out for {ticket.tool_name}"
                )

            # Check if decision has been made
            if current_ticket.status == "approved":
                logger.info(
                    f"Approval ticket {ticket.ticket_id} approved "
                    f"by {current_ticket.resolved_by}"
                )
                # Restore original tool args when available (runtime execution needs them)
                if not current_ticket.tool_args or current_ticket.tool_args == current_ticket.masked_args:
                    current_ticket.tool_args = ticket.tool_args
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

    async def get_ticket(self, ticket_id: str) -> Optional[ApprovalTicket]:
        """
        Get an approval ticket by ID.

        Args:
            ticket_id: Ticket identifier

        Returns:
            ApprovalTicket or None if not found
        """
        async with self._lock:
            ticket = self._tickets.get(ticket_id)
            if ticket is not None:
                return ticket

        if not self.ticket_store:
            return None

        try:
            record = await self.ticket_store.get_approval_ticket(ticket_id)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Failed to load approval ticket %s from storage: %s",
                ticket_id,
                exc,
            )
            return None

        if record is None:
            return None

        ticket = self._ticket_from_record(record)
        async with self._lock:
            self._tickets.setdefault(ticket.ticket_id, ticket)

        return ticket

    async def approve_ticket(
        self,
        ticket_id: str,
        approved_by: str,
        response: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> ApprovalTicket:
        """
        Approve an approval ticket.

        Args:
            ticket_id: Ticket identifier
            approved_by: User who approved
            response: Optional response data
            reason: Optional human-readable decision reason

        Returns:
            Updated ApprovalTicket

        Raises:
            ApprovalGateError: If ticket not found or already resolved
        """
        ticket = await self.get_ticket(ticket_id)
        if ticket is None:
            raise ApprovalGateError(f"Approval ticket {ticket_id} not found")

        if ticket.status != "pending":
            raise ApprovalGateError(
                f"Approval ticket {ticket_id} already {ticket.status}"
            )

        updated = await self._resolve_ticket(
            ticket,
            status="approved",
            resolved_by=approved_by,
            decision_reason=reason,
            response=response or {},
        )

        logger.info(f"Approved ticket {ticket_id} by {approved_by}")

        return updated

    async def deny_ticket(
        self,
        ticket_id: str,
        denied_by: str,
        reason: Optional[str] = None,
        response: Optional[Dict[str, Any]] = None,
    ) -> ApprovalTicket:
        """
        Deny an approval ticket.

        Args:
            ticket_id: Ticket identifier
            denied_by: User who denied
            reason: Optional reason for denial
            response: Optional response payload

        Returns:
            Updated ApprovalTicket

        Raises:
            ApprovalGateError: If ticket not found or already resolved
        """
        ticket = await self.get_ticket(ticket_id)
        if ticket is None:
            raise ApprovalGateError(f"Approval ticket {ticket_id} not found")

        if ticket.status != "pending":
            raise ApprovalGateError(
                f"Approval ticket {ticket_id} already {ticket.status}"
            )

        response_payload = response or ({"reason": reason} if reason else {})
        updated = await self._resolve_ticket(
            ticket,
            status="denied",
            resolved_by=denied_by,
            decision_reason=reason,
            response=response_payload,
        )

        logger.info(f"Denied ticket {ticket_id} by {denied_by}: {reason}")

        return updated

    async def list_pending_tickets(
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
        tickets: Dict[str, ApprovalTicket] = {}

        async with self._lock:
            for ticket in self._tickets.values():
                if ticket.status != "pending":
                    continue
                if run_id and ticket.run_id != run_id:
                    continue
                if agent_slug and ticket.agent_slug != agent_slug:
                    continue
                tickets[ticket.ticket_id] = ticket

        if self.ticket_store:
            try:
                records = await self.ticket_store.list_approval_tickets(
                    run_id=run_id,
                    agent_slug=agent_slug,
                    status="pending",
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Failed to list approval tickets from storage: %s", exc)
            else:
                for record in records:
                    if record.ticket_id in tickets:
                        continue
                    tickets[record.ticket_id] = self._ticket_from_record(record)

        pending = sorted(tickets.values(), key=lambda t: t.requested_at)

        return pending

    async def expire_old_tickets(self) -> int:
        """
        Expire old tickets that have passed their TTL.

        Returns:
            Number of tickets expired
        """
        now = datetime.now(UTC)
        expired_count = 0

        pending = await self.list_pending_tickets()
        for ticket in pending:
            if now >= ticket.expires_at:
                await self._expire_ticket(ticket)
                expired_count += 1

        if expired_count > 0:
            logger.info(f"Expired {expired_count} approval tickets")

        return expired_count

    def _ticket_to_record(self, ticket: ApprovalTicket) -> ApprovalTicketRecord:
        """Convert in-memory ticket to storage record."""
        return ApprovalTicketRecord(
            ticket_id=ticket.ticket_id,
            run_id=ticket.run_id,
            agent_slug=ticket.agent_slug,
            tool_name=ticket.tool_name,
            masked_args=dict(ticket.masked_args),
            args_hash=ticket.args_hash,
            step_id=ticket.step_id,
            metadata=dict(ticket.metadata),
            requested_at=ticket.requested_at,
            expires_at=ticket.expires_at,
            status=ticket.status,
            resolved_at=ticket.resolved_at,
            resolved_by=ticket.resolved_by,
            decision_reason=ticket.decision_reason,
            response=dict(ticket.response) if ticket.response else None,
        )

    def _ticket_from_record(self, record: ApprovalTicketRecord) -> ApprovalTicket:
        """Convert storage record to in-memory ticket."""
        return ApprovalTicket(
            ticket_id=record.ticket_id,
            run_id=record.run_id,
            agent_slug=record.agent_slug,
            tool_name=record.tool_name,
            tool_args=dict(record.masked_args),
            args_hash=record.args_hash,
            requested_at=record.requested_at,
            expires_at=record.expires_at,
            status=record.status,
            masked_args=dict(record.masked_args),
            step_id=record.step_id,
            metadata=dict(record.metadata),
            resolved_at=record.resolved_at,
            resolved_by=record.resolved_by,
            decision_reason=record.decision_reason,
            response=dict(record.response) if record.response else None,
        )

    async def _resolve_ticket(
        self,
        ticket: ApprovalTicket,
        *,
        status: ApprovalStatus,
        resolved_by: str,
        decision_reason: Optional[str],
        response: Optional[Dict[str, Any]],
    ) -> ApprovalTicket:
        """Update ticket state and persist changes."""
        ticket.status = status
        ticket.resolved_at = datetime.now(UTC)
        ticket.resolved_by = resolved_by
        ticket.decision_reason = decision_reason
        ticket.response = response or {}

        async with self._lock:
            self._tickets[ticket.ticket_id] = ticket

        if self.ticket_store:
            record = self._ticket_to_record(ticket)
            try:
                await self.ticket_store.update_approval_ticket(record)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    "Failed to update approval ticket %s: %s",
                    ticket.ticket_id,
                    exc,
                )
            else:
                await self._emit_event(
                    "approval.updated",
                    ticket,
                    message=f"Approval ticket {ticket.ticket_id} {status}",
                    extras={"resolved_by": resolved_by},
                )

        return ticket

    async def _emit_event(
        self,
        event_type: str,
        ticket: ApprovalTicket,
        message: Optional[str],
        extras: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append approval-related events to the storage backend."""
        if not self.ticket_store:
            return

        payload: Dict[str, Any] = {
            "ticket_id": ticket.ticket_id,
            "tool_name": ticket.tool_name,
            "args_hash": ticket.args_hash,
            "masked_args": ticket.masked_args,
            "status": ticket.status,
            "step_id": ticket.step_id,
            "decision_reason": ticket.decision_reason,
            "requested_at": ticket.requested_at.isoformat(),
            "expires_at": ticket.expires_at.isoformat(),
            "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
            "resolved_by": ticket.resolved_by,
            "metadata": ticket.metadata,
        }
        if extras:
            payload.update(extras)

        safe_payload = cast(Dict[str, Any], json_safe(payload))

        try:
            await self.ticket_store.append_event(
                run_id=ticket.run_id,
                agent_slug=ticket.agent_slug,
                event_type=event_type,
                timestamp=datetime.now(UTC),
                message=message,
                payload=safe_payload,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Failed to append approval event %s for ticket %s: %s",
                event_type,
                ticket.ticket_id,
                exc,
            )

    async def _expire_ticket(self, ticket: ApprovalTicket) -> ApprovalTicket:
        """Mark a ticket as expired and persist the update."""
        if ticket.status == "expired":
            return ticket

        expired_ticket = await self._resolve_ticket(
            ticket,
            status="expired",
            resolved_by="system:auto-expire",
            decision_reason="Approval request expired",
            response={"reason": "expired"},
        )

        logger.info(f"Expired ticket {ticket.ticket_id}")

        return expired_ticket

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
            metadata_payload = ctx.get("approval_metadata")
            if metadata_payload is not None and not isinstance(metadata_payload, dict):
                metadata_payload = {"value": metadata_payload}

            ticket = await self.create_ticket(
                run_id=run_id,
                agent_slug=agent_slug,
                tool_name=tool_name,
                tool_args=tool_args,
                step_id=ctx.get("step_id"),
                metadata=metadata_payload,
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
