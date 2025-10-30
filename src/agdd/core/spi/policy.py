"""Policy SPI for governance and constraint evaluation.

This module defines the PolicyProvider protocol that policy engines must implement,
enabling pluggable policy evaluation for access control, content moderation,
cost limits, and compliance requirements.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from agdd.core.types import PolicySnapshot, RunIR


class PolicyDecision(Protocol):
    """Result of policy evaluation.

    Attributes:
        allowed: Whether the action is permitted by policy.
        reason: Human-readable explanation for the decision.
        violations: List of specific policy rules that were violated (if denied).
        metadata: Optional additional context (e.g., applied rules, severity).
    """

    allowed: bool
    reason: str
    violations: list[str]
    metadata: dict[str, Any]


class PolicyProvider(Protocol):
    """Protocol for policy evaluation and enforcement implementations.

    Implementations integrate with policy engines (OPA, Cedar, custom rules) to
    evaluate access control, content moderation, cost limits, and compliance
    requirements at various lifecycle points.
    """

    async def evaluate_run_submission(
        self,
        run_ir: RunIR,
        policy_snapshot: PolicySnapshot,
        *,
        context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """Evaluate whether a run submission is permitted by policy.

        Args:
            run_ir: Complete run specification to evaluate.
            policy_snapshot: Immutable policy version to apply.
            context: Optional additional context (user identity, request metadata).

        Returns:
            PolicyDecision indicating whether submission is allowed and why.

        Note:
            This is the primary gating point for run submissions. Denied runs
            should not proceed to execution.
        """
        ...

    async def evaluate_content_moderation(
        self,
        content: str,
        content_type: Literal["input", "output"],
        policy_snapshot: PolicySnapshot,
        *,
        run_ir: RunIR | None = None,
    ) -> PolicyDecision:
        """Evaluate content against moderation policies.

        Args:
            content: Text content to moderate (input prompt or output completion).
            content_type: Whether content is "input" (user prompt) or "output"
                (model generation).
            policy_snapshot: Policy version to apply for moderation rules.
            run_ir: Optional run context for attribution and logging.

        Returns:
            PolicyDecision indicating whether content passes moderation.

        Note:
            Input moderation gates execution; output moderation may redact or
            flag content without blocking the run.
        """
        ...

    async def evaluate_cost_limit(
        self,
        estimated_cost_usd: float,
        policy_snapshot: PolicySnapshot,
        *,
        run_ir: RunIR | None = None,
        accumulated_cost_usd: float = 0.0,
    ) -> PolicyDecision:
        """Evaluate whether estimated cost is within policy limits.

        Args:
            estimated_cost_usd: Estimated cost for the operation in USD.
            policy_snapshot: Policy version defining cost limits.
            run_ir: Optional run context for budget tracking.
            accumulated_cost_usd: Total cost accumulated for this run so far.

        Returns:
            PolicyDecision indicating whether cost is within limits.

        Note:
            Should be evaluated before expensive operations (generation, batch).
            Implementations may enforce per-run, per-user, or per-org limits.
        """
        ...

    async def get_snapshot(self, policy_id: str, version: str) -> PolicySnapshot:
        """Retrieve an immutable policy snapshot by ID and version.

        Args:
            policy_id: Unique policy identifier.
            version: Semantic version string (e.g., '1.2.3').

        Returns:
            PolicySnapshot with verified content hash.

        Raises:
            ValueError: If policy ID or version does not exist.

        Note:
            Snapshots are immutable and content-addressed for audit integrity.
        """
        ...

    async def validate_snapshot(self, snapshot: PolicySnapshot) -> bool:
        """Verify that a policy snapshot is valid and content hash matches.

        Args:
            snapshot: PolicySnapshot to validate.

        Returns:
            True if snapshot is valid and hash matches stored content.

        Note:
            Should be called when loading snapshots from untrusted sources.
        """
        ...
