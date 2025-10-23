"""
Storage-backed observability logger.

Provides an improved ObservabilityLogger that uses the pluggable storage layer
instead of direct file system operations.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from agdd.storage.base import StorageBackend
from agdd.storage.models import (
    ArtifactEvent,
    DelegationEvent,
    MCPCallEvent,
    MetricEvent,
)


class StorageObservabilityLogger:
    """
    Observability logger backed by pluggable storage.

    This replaces the file-based ObservabilityLogger with a more scalable
    storage-backed implementation that supports:
    - Multiple storage backends (SQLite, PostgreSQL, etc.)
    - Full-text search
    - Structured querying
    - Automatic lifecycle management
    """

    def __init__(
        self,
        run_id: str,
        slug: str,
        storage: StorageBackend,
        parent_run_id: Optional[str] = None,
    ):
        """
        Initialize storage-backed observability logger.

        Args:
            run_id: Unique run identifier
            slug: Agent slug
            storage: Storage backend instance
            parent_run_id: Parent run ID for sub-agent delegations
        """
        self.run_id = run_id
        self.slug = slug
        self.storage = storage
        self.parent_run_id = parent_run_id
        self._metrics: Dict[str, Any] = {}
        self._started_at = datetime.now(timezone.utc)
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Ensure run record is created"""
        if not self._initialized:
            await self.storage.create_run(
                run_id=self.run_id,
                agent_slug=self.slug,
                parent_run_id=self.parent_run_id,
                started_at=self._started_at,
                status="running",
            )
            self._initialized = True

    def log(self, event: str, data: Dict[str, Any]) -> None:
        """
        Log an event (synchronous wrapper).

        Args:
            event: Event name (e.g., 'start', 'end', 'error')
            data: Event data
        """
        # Run async in event loop or create new one
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, schedule as task
                loop.create_task(self._log_async(event, data))
            else:
                # Otherwise run directly
                loop.run_until_complete(self._log_async(event, data))
        except RuntimeError:
            # No event loop, create one
            asyncio.run(self._log_async(event, data))

    async def _log_async(self, event: str, data: Dict[str, Any]) -> None:
        """Log an event (async)"""
        await self._ensure_initialized()

        # Determine log level from event type
        level = "info"
        if event in ("error", "retry"):
            level = "error"
        elif event == "warn":
            level = "warn"

        # Create message from event and data
        msg = self._format_message(event, data)

        await self.storage.append_event(
            run_id=self.run_id,
            agent_slug=self.slug,
            event_type="log",
            timestamp=datetime.now(timezone.utc),
            level=level,
            message=msg,
            payload={"event": event, **data},
        )

    def metric(self, key: str, value: Any) -> None:
        """
        Record a metric (synchronous wrapper).

        Args:
            key: Metric name
            value: Metric value
        """
        self._metrics[key] = value

        # Log as metric event
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._metric_async(key, value))
            else:
                loop.run_until_complete(self._metric_async(key, value))
        except RuntimeError:
            asyncio.run(self._metric_async(key, value))

    async def _metric_async(self, key: str, value: Any) -> None:
        """Record a metric (async)"""
        await self._ensure_initialized()

        # Determine unit from metric name
        unit = None
        if "_ms" in key:
            unit = "milliseconds"
        elif "_usd" in key or "cost" in key.lower():
            unit = "usd"
        elif "token" in key.lower():
            unit = "tokens"

        metric_event = MetricEvent(
            name=key,
            value=float(value),
            unit=unit,
        )

        await self.storage.append_event(
            run_id=self.run_id,
            agent_slug=self.slug,
            event_type="metric",
            timestamp=datetime.now(timezone.utc),
            message=f"{key}={value}",
            payload=metric_event.model_dump(),
        )

    def log_mcp_call(
        self,
        server: str,
        tool: str,
        args: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        duration_ms: int = 0,
        token_count: Optional[int] = None,
        cost_usd: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Log an MCP (Model Context Protocol) call.

        Args:
            server: MCP server name
            tool: Tool name
            args: Tool arguments
            result: Tool result
            duration_ms: Call duration in milliseconds
            token_count: Tokens consumed
            cost_usd: Cost in USD
            error: Error message if failed
        """
        mcp_event = MCPCallEvent(
            server=server,
            tool=tool,
            args=args,
            result=result,
            duration_ms=duration_ms,
            token_count=token_count,
            cost_usd=cost_usd,
            error=error,
        )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._log_mcp_async(mcp_event))
            else:
                loop.run_until_complete(self._log_mcp_async(mcp_event))
        except RuntimeError:
            asyncio.run(self._log_mcp_async(mcp_event))

    async def _log_mcp_async(self, mcp_event: MCPCallEvent) -> None:
        """Log MCP call (async)"""
        await self._ensure_initialized()

        level = "error" if mcp_event.error else "info"
        msg = f"MCP call: {mcp_event.server}.{mcp_event.tool}"

        await self.storage.append_event(
            run_id=self.run_id,
            agent_slug=self.slug,
            event_type="mcp.call",
            timestamp=datetime.now(timezone.utc),
            level=level,
            message=msg,
            payload=mcp_event.model_dump(),
        )

    def log_delegation(
        self,
        task_id: str,
        target_agent: str,
        target_run_id: Optional[str] = None,
        status: str = "pending",
    ) -> None:
        """
        Log an agent delegation event.

        Args:
            task_id: Task identifier
            target_agent: Target SAG slug
            target_run_id: Run ID of delegated execution
            status: Delegation status
        """
        delegation_event = DelegationEvent(
            task_id=task_id,
            target_agent=target_agent,
            target_run_id=target_run_id,
            status=status,
        )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._log_delegation_async(delegation_event))
            else:
                loop.run_until_complete(self._log_delegation_async(delegation_event))
        except RuntimeError:
            asyncio.run(self._log_delegation_async(delegation_event))

    async def _log_delegation_async(self, delegation_event: DelegationEvent) -> None:
        """Log delegation (async)"""
        await self._ensure_initialized()

        msg = f"Delegation: {delegation_event.task_id} -> {delegation_event.target_agent}"

        await self.storage.append_event(
            run_id=self.run_id,
            agent_slug=self.slug,
            event_type="delegation",
            timestamp=datetime.now(timezone.utc),
            message=msg,
            payload=delegation_event.model_dump(),
        )

    def log_artifact(
        self,
        name: str,
        artifact_type: str,
        artifact_uri: Optional[str] = None,
        size_bytes: Optional[int] = None,
        mime_type: Optional[str] = None,
        checksum: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an artifact creation event.

        Args:
            name: Artifact name
            artifact_type: Artifact type (code, report, data, etc.)
            artifact_uri: URI to artifact (S3, MinIO, etc.)
            size_bytes: Size in bytes
            mime_type: MIME type
            checksum: SHA-256 checksum
            metadata: Additional metadata
        """
        artifact_event = ArtifactEvent(
            name=name,
            type=artifact_type,
            size_bytes=size_bytes,
            mime_type=mime_type,
            checksum=checksum,
            metadata=metadata or {},
        )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(
                    self._log_artifact_async(artifact_event, artifact_uri)
                )
            else:
                loop.run_until_complete(
                    self._log_artifact_async(artifact_event, artifact_uri)
                )
        except RuntimeError:
            asyncio.run(self._log_artifact_async(artifact_event, artifact_uri))

    async def _log_artifact_async(
        self, artifact_event: ArtifactEvent, artifact_uri: Optional[str]
    ) -> None:
        """Log artifact (async)"""
        await self._ensure_initialized()

        msg = f"Artifact created: {artifact_event.name} ({artifact_event.type})"

        await self.storage.append_event(
            run_id=self.run_id,
            agent_slug=self.slug,
            event_type="artifact",
            timestamp=datetime.now(timezone.utc),
            message=msg,
            payload=artifact_event.model_dump(),
        )

    def finalize(self) -> None:
        """Finalize the run (mark as completed)"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._finalize_async("succeeded"))
            else:
                loop.run_until_complete(self._finalize_async("succeeded"))
        except RuntimeError:
            asyncio.run(self._finalize_async("succeeded"))

    def finalize_with_error(self, error: str) -> None:
        """Finalize the run with an error"""
        self._metrics["error"] = error

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._finalize_async("failed"))
            else:
                loop.run_until_complete(self._finalize_async("failed"))
        except RuntimeError:
            asyncio.run(self._finalize_async("failed"))

    async def _finalize_async(self, status: str) -> None:
        """Finalize run (async)"""
        await self._ensure_initialized()

        await self.storage.update_run(
            run_id=self.run_id,
            status=status,
            ended_at=datetime.now(timezone.utc),
            metrics=self._metrics,
        )

    @staticmethod
    def _format_message(event: str, data: Dict[str, Any]) -> str:
        """Format a log message from event and data"""
        if event == "start":
            return f"Started agent: {data.get('agent', data.get('slug', 'unknown'))}"
        elif event == "end":
            duration = data.get("duration_ms", 0)
            return f"Completed successfully in {duration}ms"
        elif event == "error":
            return f"Error: {data.get('error', 'unknown error')}"
        elif event == "retry":
            attempt = data.get("attempt", 0)
            return f"Retry attempt {attempt}: {data.get('error', 'unknown error')}"
        else:
            # Generic message
            return f"{event}: {data}"
