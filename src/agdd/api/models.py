"""Pydantic models for API request/response schemas."""

from __future__ import annotations

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
