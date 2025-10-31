"""
Runner hooks for integration with governance systems.

Provides hooks for integrating approval gates, MCP permissions,
and other governance features into agent runners.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from agdd.api.config import get_settings
from agdd.core.permissions import ToolPermission

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

        logger.info(
            f"Pre-tool execution: {tool_name} permission={permission.value} "
            f"(agent={context.get('agent_slug')}, run={context.get('run_id')})"
        )

        # Handle permission
        if permission == ToolPermission.NEVER:
            from agdd.governance.approval_gate import ApprovalDeniedError

            raise ApprovalDeniedError(
                f"Tool {tool_name} is not allowed by policy"
            )

        if permission == ToolPermission.REQUIRE_APPROVAL:
            # Create approval ticket and wait for decision
            ticket = self.approval_gate.create_ticket(
                run_id=context.get("run_id", "unknown"),
                agent_slug=context.get("agent_slug", "unknown"),
                tool_name=tool_name,
                tool_args=tool_args,
            )

            logger.info(
                f"Created approval ticket {ticket.ticket_id} for {tool_name}"
            )

            # Wait for approval decision
            await self.approval_gate.wait_for_decision(ticket)

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

        # Placeholder: Log to storage backend
        # await storage.append_event(
        #     run_id=context.get("run_id"),
        #     agent_slug=context.get("agent_slug"),
        #     event_type="tool.executed",
        #     payload={
        #         "tool_name": tool_name,
        #         "tool_args": tool_args,
        #         "success": True,
        #     }
        # )

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

        # Placeholder: Log error to storage backend
        # await storage.append_event(
        #     run_id=context.get("run_id"),
        #     agent_slug=context.get("agent_slug"),
        #     event_type="tool.error",
        #     level="error",
        #     message=str(error),
        #     payload={
        #         "tool_name": tool_name,
        #         "tool_args": tool_args,
        #         "error": str(error),
        #     }
        # )


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

    from agdd.governance.approval_gate import ApprovalGate
    from agdd.governance.permission_evaluator import PermissionEvaluator

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
