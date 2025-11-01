"""
Runner hooks for integration with governance systems.

Provides hooks for integrating approval gates, MCP permissions,
and other governance features into agent runners.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from magsag.api.config import get_settings
from magsag.core.permissions import ToolPermission, mask_tool_args
from magsag.governance.approval_gate import ApprovalDeniedError, ApprovalTimeoutError
from magsag.storage import get_storage_backend
from magsag.storage.serialization import json_safe

if TYPE_CHECKING:  # pragma: no cover - typing aid
    from magsag.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class RunnerHooks:
    """
    Hooks for agent runners.

    Provides integration points for approval gates, permission checks,
    and other governance features.
    """

    def __init__(
        self,
        approval_gate: Optional[Any] = None,  # ApprovalGate instance
        enable_approvals: Optional[bool] = None,
    ):
        """
        Initialize runner hooks.

        Args:
            approval_gate: Optional approval gate instance
            enable_approvals: Whether to enable approvals (default: from config)
        """
        settings = get_settings()

        self.approval_gate = approval_gate
        self.enable_approvals = (
            enable_approvals
            if enable_approvals is not None
            else settings.APPROVALS_ENABLED
        )
        self._storage_backend: Optional["StorageBackend"] = None
        self._storage_lock = asyncio.Lock()
        self._storage_disabled = False

    async def _get_storage_backend(self) -> Optional["StorageBackend"]:
        """Lazily acquire the shared storage backend for audit events."""
        if self._storage_disabled:
            return None

        if self._storage_backend is not None:
            return self._storage_backend

        async with self._storage_lock:
            if self._storage_backend is not None or self._storage_disabled:
                return self._storage_backend

            try:
                self._storage_backend = await get_storage_backend()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    "Runner hooks could not acquire storage backend: %s", exc
                )
                self._storage_disabled = True
                return None

        return self._storage_backend

    async def _record_event(
        self,
        *,
        run_id: Optional[str],
        agent_slug: Optional[str],
        event_type: str,
        message: str,
        payload: Dict[str, Any],
        level: Optional[str] = None,
    ) -> None:
        """Persist tool governance events to the central storage backend."""
        if not run_id:
            return

        storage = await self._get_storage_backend()
        if storage is None:
            return

        safe_payload = json_safe(payload)

        try:
            await storage.append_event(
                run_id=run_id,
                agent_slug=agent_slug or "unknown",
                event_type=event_type,
                timestamp=datetime.now(UTC),
                level=level,
                message=message,
                payload=safe_payload if isinstance(safe_payload, dict) else {"payload": safe_payload},
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Failed to record runner hook event %s for run %s: %s",
                event_type,
                run_id,
                exc,
            )

    async def pre_tool_execution(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: Dict[str, Any],
    ) -> None:
        """
        Hook called before tool execution.

        Performs permission checks and approval gate evaluation.

        Args:
            tool_name: Tool name
            tool_args: Tool arguments
            context: Execution context (agent_slug, run_id, etc.)

        Raises:
            ApprovalDeniedError: If tool is not allowed
            ApprovalTimeoutError: If approval times out
        """
        if not self.enable_approvals:
            logger.debug("Approvals disabled, skipping permission check")
            return

        if self.approval_gate is None:
            logger.warning(
                "Approval gate not configured, skipping permission check"
            )
            return

        # Evaluate permission
        permission = self.approval_gate.evaluate(tool_name, context)

        await self._record_event(
            run_id=context.get("run_id"),
            agent_slug=context.get("agent_slug"),
            event_type="tool.permission.checked",
            message=f"Permission evaluated for {tool_name}",
            payload={
                "tool": tool_name,
                "permission": permission.value,
                "context": json_safe(context),
            },
        )

        logger.info(
            f"Pre-tool execution: {tool_name} permission={permission.value} "
            f"(agent={context.get('agent_slug')}, run={context.get('run_id')})"
        )

        # Handle permission
        if permission == ToolPermission.NEVER:
            await self._record_event(
                run_id=context.get("run_id"),
                agent_slug=context.get("agent_slug"),
                event_type="tool.permission.denied",
                message=f"Tool {tool_name} execution blocked by policy",
                payload={
                    "tool": tool_name,
                    "permission": permission.value,
                },
                level="error",
            )
            raise ApprovalDeniedError(
                f"Tool {tool_name} is not allowed by policy"
            )

        if permission == ToolPermission.REQUIRE_APPROVAL:
            # Create approval ticket and wait for decision
            metadata_payload = context.get("approval_metadata")
            if metadata_payload is not None and not isinstance(metadata_payload, dict):
                metadata_payload = {"value": metadata_payload}

            ticket = await self.approval_gate.create_ticket(
                run_id=context.get("run_id", "unknown"),
                agent_slug=context.get("agent_slug", "unknown"),
                tool_name=tool_name,
                tool_args=tool_args,
                step_id=context.get("step_id"),
                metadata=metadata_payload,
            )

            logger.info(
                f"Created approval ticket {ticket.ticket_id} for {tool_name}"
            )

            await self._record_event(
                run_id=context.get("run_id"),
                agent_slug=context.get("agent_slug"),
                event_type="tool.approval.requested",
                message=f"Approval requested for {tool_name}",
                payload={
                    "tool": tool_name,
                    "ticket_id": ticket.ticket_id,
                    "masked_args": mask_tool_args(tool_args),
                },
            )

            # Wait for approval decision
            try:
                decision = await self.approval_gate.wait_for_decision(ticket)
            except ApprovalTimeoutError as exc:
                await self._record_event(
                    run_id=context.get("run_id"),
                    agent_slug=context.get("agent_slug"),
                    event_type="tool.approval.timeout",
                    message=f"Approval timed out for {tool_name}",
                    payload={
                        "tool": tool_name,
                        "ticket_id": ticket.ticket_id,
                        "reason": str(exc),
                    },
                    level="error",
                )
                raise
            except ApprovalDeniedError as exc:
                await self._record_event(
                    run_id=context.get("run_id"),
                    agent_slug=context.get("agent_slug"),
                    event_type="tool.approval.denied",
                    message=f"Approval denied for {tool_name}",
                    payload={
                        "tool": tool_name,
                        "ticket_id": ticket.ticket_id,
                        "reason": str(exc),
                    },
                    level="error",
                )
                raise
            else:
                await self._record_event(
                    run_id=context.get("run_id"),
                    agent_slug=context.get("agent_slug"),
                    event_type="tool.approval.granted",
                    message=f"Approval granted for {tool_name}",
                    payload={
                        "tool": tool_name,
                        "ticket_id": decision.ticket_id,
                        "resolved_by": decision.resolved_by,
                        "decision_reason": decision.decision_reason,
                    },
                )

            logger.info(
                f"Tool {tool_name} approved, proceeding with execution"
            )

        # ALWAYS permission: proceed without approval

    async def post_tool_execution(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        result: Any,
        context: Dict[str, Any],
    ) -> None:
        """
        Hook called after tool execution.

        Can be used for logging, metrics, audit trail, etc.

        Args:
            tool_name: Tool name
            tool_args: Tool arguments
            result: Tool execution result
            context: Execution context
        """
        logger.info(
            f"Post-tool execution: {tool_name} "
            f"(agent={context.get('agent_slug')}, run={context.get('run_id')})"
        )

        await self._record_event(
            run_id=context.get("run_id"),
            agent_slug=context.get("agent_slug"),
            event_type="tool.executed",
            message=f"Tool {tool_name} executed successfully",
            payload={
                "tool": tool_name,
                "masked_args": mask_tool_args(tool_args),
                "result": json_safe(result),
            },
        )

    async def on_tool_error(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        error: Exception,
        context: Dict[str, Any],
    ) -> None:
        """
        Hook called when tool execution fails.

        Args:
            tool_name: Tool name
            tool_args: Tool arguments
            error: Exception that occurred
            context: Execution context
        """
        logger.error(
            f"Tool execution error: {tool_name} - {error} "
            f"(agent={context.get('agent_slug')}, run={context.get('run_id')})"
        )

        await self._record_event(
            run_id=context.get("run_id"),
            agent_slug=context.get("agent_slug"),
            event_type="tool.error",
            message=f"Tool {tool_name} raised {type(error).__name__}",
            payload={
                "tool": tool_name,
                "masked_args": mask_tool_args(tool_args),
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
            level="error",
        )


def create_approval_gate_hook(
    policy_path: Optional[str] = None,
) -> RunnerHooks:
    """
    Create runner hooks with approval gate integration.

    Args:
        policy_path: Optional path to tool permissions policy

    Returns:
        RunnerHooks instance with approval gate configured
    """
    settings = get_settings()

    if not settings.APPROVALS_ENABLED:
        logger.info("Approvals disabled, creating hooks without approval gate")
        return RunnerHooks(enable_approvals=False)

    from pathlib import Path

    from magsag.governance.approval_gate import ApprovalGate
    from magsag.governance.permission_evaluator import PermissionEvaluator

    # Create permission evaluator
    policy_file = Path(policy_path) if policy_path else None
    evaluator = PermissionEvaluator(policy_path=policy_file)

    # Create approval gate
    approval_gate = ApprovalGate(
        permission_evaluator=evaluator,
        default_timeout_minutes=settings.APPROVAL_TTL_MIN,
    )

    logger.info("Created runner hooks with approval gate integration")

    return RunnerHooks(
        approval_gate=approval_gate,
        enable_approvals=True,
    )


async def execute_with_hooks(
    tool_fn: Callable[..., Any],
    tool_name: str,
    tool_args: Dict[str, Any],
    hooks: RunnerHooks,
    context: Dict[str, Any],
) -> Any:
    """
    Execute a tool with runner hooks.

    Wraps tool execution with pre/post hooks and error handling.

    Args:
        tool_fn: Tool function to execute
        tool_name: Tool name
        tool_args: Tool arguments
        hooks: Runner hooks instance
        context: Execution context

    Returns:
        Tool execution result

    Raises:
        Any exceptions from tool or hooks
    """
    try:
        # Pre-execution hook
        await hooks.pre_tool_execution(tool_name, tool_args, context)

        # Execute tool
        result = await tool_fn(**tool_args)

        # Post-execution hook
        await hooks.post_tool_execution(tool_name, tool_args, result, context)

        return result

    except Exception as e:
        # Error hook
        await hooks.on_tool_error(tool_name, tool_args, e, context)
        raise
