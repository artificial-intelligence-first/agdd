"""Pydantic models for API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentRunRequest(BaseModel):
    """Request payload for running an agent."""

    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any] = Field(..., description="Agent input payload conforming to contract")
    request_id: str | None = Field(default=None, description="Optional request tracking ID")
    metadata: dict[str, Any] | None = Field(default=None, description="Optional metadata")


class AgentInfo(BaseModel):
    """Agent metadata from registry."""

    slug: str = Field(..., description="Agent slug identifier")
    title: str | None = Field(default=None, description="Human-readable agent title")
    description: str | None = Field(default=None, description="Agent description")


class AgentRunResponse(BaseModel):
    """Response from agent execution."""

    run_id: str | None = Field(default=None, description="Unique run identifier")
    slug: str = Field(..., description="Agent slug that was executed")
    output: dict[str, Any] = Field(..., description="Agent output conforming to contract")
    artifacts: dict[str, str] | None = Field(
        default=None, description="URLs/paths to observability artifacts"
    )


class RunSummary(BaseModel):
    """Summary of a completed agent run."""

    run_id: str = Field(..., description="Unique run identifier")
    slug: str | None = Field(default=None, description="Agent slug")
    summary: dict[str, Any] | None = Field(
        default=None, description="Summary data from summary.json"
    )
    metrics: dict[str, Any] | None = Field(
        default=None, description="Metrics data from metrics.json"
    )
    has_logs: bool = Field(..., description="Whether logs.jsonl exists")


class CreateRunRequest(BaseModel):
    """Request payload for creating a new agent run via POST /runs."""

    model_config = ConfigDict(extra="forbid")

    agent: str = Field(..., description="Agent slug identifier to execute")
    payload: dict[str, Any] = Field(..., description="Agent input payload conforming to contract")
    idempotency_key: str | None = Field(
        default=None, description="Optional idempotency key for duplicate prevention"
    )


class CreateRunResponse(BaseModel):
    """Response from creating a new agent run."""

    run_id: str = Field(..., description="Unique run identifier")
    status: str = Field(..., description="Run status (e.g., 'started', 'completed')")


class ApiError(BaseModel):
    """Standard API error response."""

    code: Literal[
        "agent_not_found",
        "invalid_payload",
        "invalid_run_id",
        "invalid_signature",
        "execution_failed",
        "not_found",
        "unauthorized",
        "rate_limit_exceeded",
        "internal_error",
        "conflict",
    ] = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(default=None, description="Additional error context")


class WorktreeCreateRequest(BaseModel):
    """Request payload for creating a new worktree."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., description="Unique identifier for the AI task run")
    task: str = Field(..., description="Task slug or summary for the worktree")
    base: str = Field(..., description="Base branch or commit-ish to start from")
    detach: bool = Field(default=False, description="Create a detached worktree without branch")
    no_checkout: bool = Field(
        default=False, description="Create worktree without populating working tree"
    )
    lock: bool = Field(default=False, description="Lock the worktree immediately after creation")
    lock_reason: str | None = Field(
        default=None, description="Optional lock reason applied after creation"
    )


class WorktreeLockRequest(BaseModel):
    """Request payload for locking a worktree."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, description="Optional lock reason")


class WorktreeMaintenanceRequest(BaseModel):
    """Request payload for GC operations."""

    model_config = ConfigDict(extra="forbid")

    expire: str | None = Field(
        default=None, description="Expiration horizon passed to git worktree prune"
    )


class WorktreeResponse(BaseModel):
    """Response schema describing a managed worktree."""

    id: str = Field(..., description="Worktree directory name")
    path: str = Field(..., description="Filesystem path to the worktree")
    run_id: str | None = Field(default=None, description="Associated run identifier")
    task: str | None = Field(default=None, description="Associated task slug")
    branch: str | None = Field(default=None, description="Checked out branch (if any)")
    head: str | None = Field(default=None, description="HEAD commit hash")
    base: str | None = Field(default=None, description="Base branch or commit used at creation")
    short_sha: str | None = Field(default=None, description="Short SHA resolved from base")
    locked: bool = Field(default=False, description="Whether the worktree is locked")
    lock_reason: str | None = Field(default=None, description="Reason supplied for lock")
    detached: bool = Field(default=False, description="Worktree created in detached HEAD mode")
    no_checkout: bool = Field(default=False, description="Worktree was created with --no-checkout")
    prunable: bool = Field(default=False, description="Git reports the worktree as prunable")
    prunable_reason: str | None = Field(
        default=None, description="Reason Git marked the worktree prunable"
    )
    created_at: datetime | None = Field(
        default=None, description="Timestamp when the worktree metadata was written"
    )
