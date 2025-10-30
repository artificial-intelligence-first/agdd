"""Core Intermediate Representation (IR) types for AGDD.

This module defines the foundational data structures for agent execution:
- CapabilityMatrix: Provider feature support matrix
- PolicySnapshot: Immutable policy version reference
- PlanIR: Execution plan with provider selection and configuration
- RunIR: Complete agent run specification with tracing metadata
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CapabilityMatrix(BaseModel):
    """Provider capability support matrix.

    Indicates which advanced features a provider implementation supports,
    enabling intelligent routing and fallback strategies.
    """

    tools: bool = Field(..., description="Support for function/tool calling")
    structured_output: bool = Field(..., description="Support for schema-constrained generation")
    vision: bool = Field(..., description="Support for image/visual input processing")
    audio: bool = Field(..., description="Support for audio input processing")


class PolicySnapshot(BaseModel):
    """Immutable reference to a policy configuration version.

    Captures the exact policy state at run submission time to ensure
    deterministic evaluation and audit trail consistency.
    """

    id: str = Field(..., description="Unique policy identifier")
    version: str = Field(..., description="Semantic version string (e.g., '1.2.3')")
    content_hash: str = Field(
        ..., description="SHA256 hash of policy content for integrity verification"
    )


class PlanIR(BaseModel):
    """Execution plan intermediate representation.

    Describes how an agent run should be executed, including provider selection,
    model configuration, optimization flags, and fallback strategies.
    """

    chain: list[dict[str, Any]] = Field(
        ..., description="Ordered list of fallback steps, each with provider/model config"
    )
    provider: str = Field(..., description="Primary provider identifier (e.g., 'openai', 'anthropic')")
    model: str = Field(..., description="Model identifier within provider namespace")
    use_batch: bool = Field(
        ..., description="Whether to use batch API for cost optimization"
    )
    use_cache: bool = Field(
        ..., description="Whether to enable prompt caching for repeated prefixes"
    )
    structured_output: bool = Field(
        ..., description="Whether to enforce structured output via schema"
    )
    moderation: bool = Field(
        ..., description="Whether to apply content moderation policies"
    )
    sla_ms: int = Field(
        ..., description="Service level agreement target latency in milliseconds"
    )
    cost_budget: float | None = Field(
        default=None, description="Optional maximum cost budget in USD"
    )


class RunIR(BaseModel):
    """Complete agent run specification intermediate representation.

    Encapsulates all information needed to execute and trace an agent run,
    including input, execution plan, policy context, and observability metadata.
    """

    run_id: str = Field(..., description="Unique run identifier (UUID)")
    agent: str = Field(..., description="Agent slug/identifier")
    input: dict[str, Any] = Field(..., description="Agent input payload")
    plan: PlanIR | None = Field(
        default=None, description="Execution plan (None if routing deferred)"
    )
    policy: PolicySnapshot = Field(
        ..., description="Immutable policy snapshot for this run"
    )
    capabilities: CapabilityMatrix = Field(
        ..., description="Required capabilities for this run"
    )
    idempotency_key: str | None = Field(
        default=None,
        description="Optional key for idempotent run deduplication",
    )
    trace_id: str = Field(
        ..., description="Distributed tracing identifier for observability"
    )
