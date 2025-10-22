"""Pydantic models for API request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    """Base model that forbids unexpected fields."""

    model_config = ConfigDict(extra="forbid")


class AgentRunRequest(StrictBaseModel):
    """Request payload for running an agent."""

    payload: dict[str, Any] = Field(..., description="Agent input payload conforming to contract")
    request_id: str | None = Field(default=None, description="Optional request tracking ID")
    metadata: dict[str, Any] | None = Field(default=None, description="Optional metadata")


class AgentInfo(StrictBaseModel):
    """Agent metadata from registry."""

    slug: str = Field(..., description="Agent slug identifier")
    title: str | None = Field(default=None, description="Human-readable agent title")
    description: str | None = Field(default=None, description="Agent description")


class AgentRunResponse(StrictBaseModel):
    """Response from agent execution."""

    run_id: str | None = Field(default=None, description="Unique run identifier")
    slug: str = Field(..., description="Agent slug that was executed")
    output: dict[str, Any] = Field(..., description="Agent output conforming to contract")
    artifacts: dict[str, str] | None = Field(
        default=None, description="URLs/paths to observability artifacts"
    )


class RunSummary(StrictBaseModel):
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


class ApiError(StrictBaseModel):
    """Standard API error response."""

    code: Literal[
        "agent_not_found",
        "invalid_payload",
        "execution_failed",
        "not_found",
        "unauthorized",
        "rate_limit_exceeded",
        "internal_error",
    ] = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(default=None, description="Additional error context")
