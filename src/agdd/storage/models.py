"""
Data models for AGDD storage.

Defines the "event envelope" pattern: strongly-typed common fields
for queryability, with flexible JSON payloads for agent-specific data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Event(BaseModel):
    """
    Event envelope - represents any observable event during agent execution.

    Common fields are strongly typed for efficient querying and indexing.
    Agent-specific data goes in the payload field as flexible JSON.
    """

    # Core identification
    ts: datetime = Field(description="Event timestamp")
    run_id: str = Field(description="Unique run identifier")
    agent_slug: str = Field(description="Agent slug (MAG/SAG identifier)")

    # Event classification
    type: str = Field(
        description=(
            "Event type: log, mcp.call, metric, artifact, delegation, "
            "approval.required, approval.updated, handoff.request, handoff.result, "
            "run.snapshot.saved, run.resume, memory.write, memory.read, etc."
        )
    )
    level: Optional[str] = Field(default=None, description="Log level: debug, info, warn, error")

    # Message & payload
    msg: Optional[str] = Field(default=None, description="Human-readable message")
    payload: Dict[str, Any] = Field(
        default_factory=dict, description="Agent-specific flexible data"
    )

    # Distributed tracing (OpenTelemetry compatible)
    span_id: Optional[str] = Field(default=None, description="Span identifier")
    parent_span_id: Optional[str] = Field(default=None, description="Parent span ID")

    # Contract versioning
    contract_id: Optional[str] = Field(default=None, description="JSON Schema contract identifier")
    contract_version: Optional[str] = Field(default=None, description="Contract version")

    # Artifacts
    artifact_uri: Optional[str] = Field(
        default=None, description="URI to associated artifact (S3, MinIO, etc.)"
    )


class Run(BaseModel):
    """
    Run metadata - represents a single agent execution.

    Tracks lifecycle, status, and aggregated metrics for a run.
    """

    run_id: str = Field(description="Unique run identifier")
    agent_slug: str = Field(description="Agent slug")
    parent_run_id: Optional[str] = Field(
        default=None, description="Parent run ID for sub-agent delegations"
    )

    started_at: datetime = Field(description="Start timestamp")
    ended_at: Optional[datetime] = Field(default=None, description="End timestamp")

    status: str = Field(
        default="running",
        description="Run status: running, succeeded, failed, canceled",
    )

    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Aggregated metrics: duration_ms, token_count, cost_usd, etc.",
    )

    tags: List[str] = Field(
        default_factory=list, description="Tags for categorization and filtering"
    )


class MCPCallEvent(BaseModel):
    """
    Model Context Protocol call event.

    Specialized event type for tracking MCP server/tool invocations.
    This gets stored in Event.payload for type='mcp.call'.
    """

    server: str = Field(description="MCP server name")
    tool: str = Field(description="Tool name")
    args: Dict[str, Any] = Field(description="Tool arguments")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Tool result")
    duration_ms: int = Field(description="Call duration in milliseconds")
    token_count: Optional[int] = Field(default=None, description="Tokens consumed")
    cost_usd: Optional[float] = Field(default=None, description="Cost in USD")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class DelegationEvent(BaseModel):
    """
    Agent delegation event.

    Tracks when a MAG delegates to a SAG.
    This gets stored in Event.payload for type='delegation'.
    """

    task_id: str = Field(description="Task identifier")
    target_agent: str = Field(description="Target SAG slug")
    target_run_id: Optional[str] = Field(default=None, description="Run ID of delegated execution")
    status: str = Field(description="Delegation status: pending, running, succeeded, failed")


class MetricEvent(BaseModel):
    """
    Metric observation event.

    Records a measured value at a point in time.
    This gets stored in Event.payload for type='metric'.
    """

    name: str = Field(description="Metric name (e.g., duration_ms, token_count)")
    value: float = Field(description="Metric value")
    unit: Optional[str] = Field(default=None, description="Unit of measurement")
    tags: Dict[str, str] = Field(default_factory=dict, description="Additional metric tags")


class ArtifactEvent(BaseModel):
    """
    Artifact creation event.

    Tracks generated artifacts (code, reports, etc.).
    This gets stored in Event.payload for type='artifact'.
    """

    name: str = Field(description="Artifact name")
    type: str = Field(description="Artifact type: code, report, data, etc.")
    size_bytes: Optional[int] = Field(default=None, description="Size in bytes")
    mime_type: Optional[str] = Field(default=None, description="MIME type")
    checksum: Optional[str] = Field(default=None, description="SHA-256 checksum")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
