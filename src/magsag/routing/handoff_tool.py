"""
Handoff-as-a-Tool implementation for agent delegation.

Provides a standardized tool interface for agents to delegate work
to other agents or systems with policy enforcement and observability.
"""

from __future__ import annotations

import logging
import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, List, Literal, Optional, Protocol, TYPE_CHECKING
from uuid import uuid4

from magsag.core.permissions import ToolPermission
from magsag.storage import get_storage_backend

if TYPE_CHECKING:
    class AgentRunnerProtocol(Protocol):
        def invoke_mag(
            self,
            slug: str,
            payload: Dict[str, Any],
            context: Optional[Dict[str, Any]] = ...,
        ) -> Dict[str, Any]:
            ...

    from magsag.storage.base import StorageBackend

logger = logging.getLogger(__name__)


HandoffStatus = Literal["pending", "in_progress", "completed", "failed", "rejected"]


@dataclass
class HandoffRequest:
    """
    Request to handoff work to another agent or system.

    Captures all information needed to route and execute the delegation.
    """

    handoff_id: str
    source_agent: str
    target_agent: str
    task: str
    context: Dict[str, Any] = field(default_factory=dict)
    payload: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: HandoffStatus = "pending"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert handoff request to dictionary."""
        return {
            "handoff_id": self.handoff_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "task": self.task,
            "context": self.context,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


class HandoffAdapter(Protocol):
    """
    Protocol for platform-specific handoff adapters.

    Each platform (MAGSAG, ADK, OpenAI, Anthropic) implements this protocol
    to handle handoff requests in its native format.
    """

    def supports_platform(self, platform: str) -> bool:
        """Check if adapter supports a platform."""
        ...

    async def execute_handoff(
        self, request: HandoffRequest
    ) -> Dict[str, Any]:
        """Execute the handoff and return results."""
        ...

    def format_tool_schema(self) -> Dict[str, Any]:
        """Return platform-specific tool schema."""
        ...


class MAGSAGHandoffAdapter:
    """
    Handoff adapter for MAGSAG native agents.

    Delegates to other MAGSAG agents using the standard invoke_mag/invoke_sag interface.
    """

    def __init__(self, runner: Optional["AgentRunnerProtocol"] = None):
        """Initialize adapter with optional AgentRunner reference."""
        self.runner = runner

    def supports_platform(self, platform: str) -> bool:
        """Check if adapter supports MAGSAG platform."""
        return platform.lower() in ("magsag", "native")

    async def execute_handoff(
        self, request: HandoffRequest
    ) -> Dict[str, Any]:
        """
        Execute handoff to another MAGSAG agent.

        Args:
            request: Handoff request

        Returns:
            Result dictionary from target agent
        """
        logger.info(
            f"Executing MAGSAG handoff from {request.source_agent} "
            f"to {request.target_agent}"
        )

        payload = request.payload or {
            "task": request.task,
            "context": request.context,
        }

        if self.runner is None:
            return {
                "status": "completed",
                "message": f"Handed off to {request.target_agent} (runner not configured)",
                "handoff_id": request.handoff_id,
            }

        run_context = dict(request.context)
        run_context.setdefault("handoff_id", request.handoff_id)
        run_context.setdefault("handoff_source_agent", request.source_agent)
        run_context.setdefault("handoff_platform", request.metadata.get("platform"))
        parent_run = request.metadata.get("run_id")
        if parent_run:
            run_context.setdefault("parent_run_id", parent_run)

        agent_output = await asyncio.to_thread(
            self.runner.invoke_mag,
            request.target_agent,
            payload,
            context=run_context,
        )

        return {
            "status": "success",
            "handoff_id": request.handoff_id,
            "agent": request.target_agent,
            "output": agent_output,
        }

    def format_tool_schema(self) -> Dict[str, Any]:
        """Return MAGSAG-compatible tool schema."""
        return {
            "name": "handoff",
            "description": "Delegate work to another agent or system",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_agent": {
                        "type": "string",
                        "description": "Agent slug or identifier to delegate to",
                    },
                    "task": {
                        "type": "string",
                        "description": "Task description for the target agent",
                    },
                    "context": {
                        "type": "object",
                        "description": "Additional context to pass to target agent",
                    },
                },
                "required": ["target_agent", "task"],
            },
        }


class ADKHandoffAdapter:
    """
    Handoff adapter for Anthropic ADK agents.

    Formats handoff requests in ADK-compatible format.
    """

    def supports_platform(self, platform: str) -> bool:
        """Check if adapter supports ADK platform."""
        return platform.lower() in ("adk", "anthropic-adk")

    async def execute_handoff(
        self, request: HandoffRequest
    ) -> Dict[str, Any]:
        """
        Execute handoff to ADK agent.

        Args:
            request: Handoff request

        Returns:
            Result dictionary
        """
        logger.info(
            f"Executing ADK handoff from {request.source_agent} "
            f"to {request.target_agent}"
        )

        # External ADK integration is handled by platform-specific adapters.
        return {
            "status": "completed",
            "message": f"Handed off to ADK agent {request.target_agent}",
            "handoff_id": request.handoff_id,
        }

    def format_tool_schema(self) -> Dict[str, Any]:
        """Return ADK-compatible tool schema."""
        return {
            "name": "handoff",
            "description": "Transfer conversation to another specialized agent",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Target agent identifier",
                    },
                    "message": {
                        "type": "string",
                        "description": "Message to pass to target agent",
                    },
                    "context": {
                        "type": "object",
                        "description": "Contextual information",
                    },
                },
                "required": ["target", "message"],
            },
        }


class OpenAIHandoffAdapter:
    """
    Handoff adapter for OpenAI-compatible agents.

    Formats handoff requests using OpenAI function calling format.
    """

    def supports_platform(self, platform: str) -> bool:
        """Check if adapter supports OpenAI platform."""
        return platform.lower() in ("openai", "openai-compat")

    async def execute_handoff(
        self, request: HandoffRequest
    ) -> Dict[str, Any]:
        """
        Execute handoff to OpenAI-compatible agent.

        Args:
            request: Handoff request

        Returns:
            Result dictionary
        """
        logger.info(
            f"Executing OpenAI handoff from {request.source_agent} "
            f"to {request.target_agent}"
        )

        # OpenAI-compatible integrations should be supplied by the calling environment.
        return {
            "status": "completed",
            "message": f"Handed off to OpenAI agent {request.target_agent}",
            "handoff_id": request.handoff_id,
        }

    def format_tool_schema(self) -> Dict[str, Any]:
        """Return OpenAI function calling schema."""
        return {
            "type": "function",
            "function": {
                "name": "handoff",
                "description": "Delegate task to another agent",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Target agent ID",
                        },
                        "instructions": {
                            "type": "string",
                            "description": "Instructions for the target agent",
                        },
                        "context": {
                            "type": "object",
                            "description": "Additional context",
                        },
                    },
                    "required": ["agent_id", "instructions"],
                },
            },
        }


class AnthropicHandoffAdapter:
    """
    Handoff adapter for Anthropic Claude API agents.

    Formats handoff requests using Anthropic tool calling format.
    """

    def supports_platform(self, platform: str) -> bool:
        """Check if adapter supports Anthropic platform."""
        return platform.lower() in ("anthropic", "claude")

    async def execute_handoff(
        self, request: HandoffRequest
    ) -> Dict[str, Any]:
        """
        Execute handoff to Anthropic agent.

        Args:
            request: Handoff request

        Returns:
            Result dictionary
        """
        logger.info(
            f"Executing Anthropic handoff from {request.source_agent} "
            f"to {request.target_agent}"
        )

        # Anthropic-specific execution is provided by external adapters.
        return {
            "status": "completed",
            "message": f"Handed off to Anthropic agent {request.target_agent}",
            "handoff_id": request.handoff_id,
        }

    def format_tool_schema(self) -> Dict[str, Any]:
        """Return Anthropic tool schema."""
        return {
            "name": "handoff",
            "description": "Delegate work to a specialized agent",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_agent": {
                        "type": "string",
                        "description": "Target agent name or ID",
                    },
                    "request": {
                        "type": "string",
                        "description": "What you need the target agent to do",
                    },
                    "context": {
                        "type": "object",
                        "description": "Relevant context for the target agent",
                    },
                },
                "required": ["target_agent", "request"],
            },
        }


class HandoffTool:
    """
    Handoff-as-a-Tool implementation with policy enforcement.

    Provides a unified tool interface for agent delegation across
    multiple platforms (MAGSAG, ADK, OpenAI, Anthropic).
    """

    def __init__(
        self,
        permission_evaluator: Optional[Any] = None,
        approval_gate: Optional[Any] = None,
        agent_runner: Optional["AgentRunnerProtocol"] = None,
        adapters: Optional[List[HandoffAdapter]] = None,
    ):
        """
        Initialize handoff tool.

        Args:
            permission_evaluator: Permission evaluator for policy checks
            approval_gate: Approval gate for REQUIRE_APPROVAL policy
            agent_runner: Optional AgentRunner for MAGSAG handoffs
            adapters: Optional explicit adapters list
        """
        self.permission_evaluator = permission_evaluator
        self.approval_gate = approval_gate

        # Register platform adapters
        self.adapters: List[HandoffAdapter] = adapters or [
            MAGSAGHandoffAdapter(runner=agent_runner),
            ADKHandoffAdapter(),
            OpenAIHandoffAdapter(),
            AnthropicHandoffAdapter(),
        ]

        # In-memory request tracking
        self._requests: Dict[str, HandoffRequest] = {}
        self._storage_backend: Optional["StorageBackend"] = None
        self._storage_lock = asyncio.Lock()

    def get_adapter(self, platform: str) -> Optional[HandoffAdapter]:
        """
        Get adapter for a specific platform.

        Args:
            platform: Platform identifier (magsag, adk, openai, anthropic)

        Returns:
            HandoffAdapter or None if not supported
        """
        for adapter in self.adapters:
            if adapter.supports_platform(platform):
                return adapter
        return None

    def get_tool_schema(self, platform: str = "magsag") -> Dict[str, Any]:
        """
        Get platform-specific tool schema.

        Args:
            platform: Platform identifier

        Returns:
            Tool schema dictionary
        """
        adapter = self.get_adapter(platform)
        if adapter is None:
            raise ValueError(f"Unsupported platform: {platform}")

        return adapter.format_tool_schema()

    async def handoff(
        self,
        source_agent: str,
        target_agent: str,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        platform: str = "magsag",
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a handoff to another agent.

        Args:
            source_agent: Source agent slug
            target_agent: Target agent slug or identifier
            task: Task description
            context: Additional context
            payload: Structured payload for execution (optional)
            platform: Target platform (magsag, adk, openai, anthropic)
            run_id: Optional run ID for tracking

        Returns:
            Result dictionary with handoff_id and status

        Raises:
            ValueError: If platform not supported
            PermissionError: If handoff is not allowed by policy
        """
        # Create handoff request
        request = HandoffRequest(
            handoff_id=str(uuid4()),
            source_agent=source_agent,
            target_agent=target_agent,
            task=task,
            context=context or {},
            payload=payload,
            metadata={"platform": platform, "run_id": run_id},
        )

        # Check permissions if evaluator is available
        if self.permission_evaluator:
            permission = self.permission_evaluator.evaluate(
                tool_name="handoff",
                context={
                    "agent_slug": source_agent,
                    "run_id": run_id,
                    "target_agent": target_agent,
                    "platform": platform,
                },
            )

            if permission == ToolPermission.NEVER:
                request.status = "rejected"
                request.error = "Handoff not allowed by policy"
                self._requests[request.handoff_id] = request
                raise PermissionError(f"Handoff to {target_agent} not allowed by policy")

            if permission == ToolPermission.REQUIRE_APPROVAL:
                # Require approval via approval gate
                if not self.approval_gate:
                    request.status = "rejected"
                    request.error = "Approval required but approval gate not configured"
                    self._requests[request.handoff_id] = request
                    raise PermissionError(
                        f"Handoff to {target_agent} requires approval but approval gate is not configured"
                    )

                # Create approval ticket
                logger.info(f"Handoff to {target_agent} requires approval, creating ticket")
                ticket_metadata = {
                    "handoff": {
                        "target_agent": target_agent,
                        "platform": platform,
                    }
                }

                ticket = await self.approval_gate.create_ticket(
                    run_id=run_id or "unknown",
                    agent_slug=source_agent,
                    tool_name="handoff",
                    tool_args={
                        "target_agent": target_agent,
                        "task": task,
                        "platform": platform,
                    },
                    metadata=ticket_metadata,
                )

                # Wait for approval decision
                try:
                    await self.approval_gate.wait_for_decision(ticket)
                    logger.info(f"Handoff to {target_agent} approved (ticket {ticket.ticket_id})")
                except Exception as e:
                    # Approval denied or timed out
                    request.status = "rejected"
                    request.error = f"Approval denied: {str(e)}"
                    self._requests[request.handoff_id] = request
                    raise PermissionError(f"Handoff to {target_agent} denied: {str(e)}") from e

        await self._record_event(
            run_id=run_id,
            agent_slug=source_agent,
            event_type="handoff.requested",
            message=f"Handoff requested to {target_agent} ({platform})",
            payload={
                "handoff_id": request.handoff_id,
                "target_agent": target_agent,
                "platform": platform,
                "task": task,
            },
        )

        # Get adapter for platform
        adapter = self.get_adapter(platform)
        if adapter is None:
            request.status = "failed"
            request.error = f"Unsupported platform: {platform}"
            self._requests[request.handoff_id] = request
            raise ValueError(f"Unsupported platform: {platform}")

        # Execute handoff
        try:
            request.status = "in_progress"
            self._requests[request.handoff_id] = request

            result = await adapter.execute_handoff(request)

            request.status = "completed"
            request.result = result
            self._requests[request.handoff_id] = request

            logger.info(
                f"Handoff {request.handoff_id} completed: "
                f"{source_agent} → {target_agent}"
            )

            await self._record_event(
                run_id=run_id,
                agent_slug=source_agent,
                event_type="handoff.completed",
                message=f"Handoff {request.handoff_id} completed",
                payload={
                    "handoff_id": request.handoff_id,
                    "target_agent": target_agent,
                    "platform": platform,
                    "result": result,
                },
            )

            return {
                "handoff_id": request.handoff_id,
                "status": "completed",
                "result": result,
            }

        except Exception as e:
            request.status = "failed"
            request.error = str(e)
            self._requests[request.handoff_id] = request

            logger.error(f"Handoff {request.handoff_id} failed: {e}")

            await self._record_event(
                run_id=run_id,
                agent_slug=source_agent,
                event_type="handoff.failed",
                message=f"Handoff {request.handoff_id} failed",
                payload={
                    "handoff_id": request.handoff_id,
                    "target_agent": target_agent,
                    "platform": platform,
                    "error": str(e),
                },
            )

            raise

    async def _get_storage(self) -> Optional["StorageBackend"]:
        if self._storage_backend is not None:
            return self._storage_backend

        async with self._storage_lock:
            if self._storage_backend is None:
                try:
                    self._storage_backend = await get_storage_backend()
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.warning("Failed to acquire storage backend for handoff events: %s", exc)
                    return None

        return self._storage_backend

    async def _record_event(
        self,
        *,
        run_id: Optional[str],
        agent_slug: str,
        event_type: str,
        message: str,
        payload: Dict[str, Any],
    ) -> None:
        if not run_id:
            return

        storage = await self._get_storage()
        if storage is None:
            return

        try:
            await storage.append_event(
                run_id=run_id,
                agent_slug=agent_slug,
                event_type=event_type,
                timestamp=datetime.now(UTC),
                message=message,
                payload=payload,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Failed to record handoff event %s for run %s: %s",
                event_type,
                run_id,
                exc,
            )

    def get_handoff(self, handoff_id: str) -> Optional[HandoffRequest]:
        """
        Get handoff request by ID.

        Args:
            handoff_id: Handoff request ID

        Returns:
            HandoffRequest or None if not found
        """
        return self._requests.get(handoff_id)

    def list_handoffs(
        self,
        source_agent: Optional[str] = None,
        status: Optional[HandoffStatus] = None,
    ) -> List[HandoffRequest]:
        """
        List handoff requests with optional filters.

        Args:
            source_agent: Filter by source agent
            status: Filter by status

        Returns:
            List of HandoffRequests
        """
        requests = list(self._requests.values())

        if source_agent:
            requests = [r for r in requests if r.source_agent == source_agent]

        if status:
            requests = [r for r in requests if r.status == status]

        # Sort by creation time (newest first)
        requests.sort(key=lambda r: r.created_at, reverse=True)

        return requests
