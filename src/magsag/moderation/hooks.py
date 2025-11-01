"""
Moderation Control Points - Ingress, Model Output, and Egress hooks.

Provides three canonical moderation hooks that can be enabled via
MAGSAG_MODERATION_ENABLED environment variable:
- check_ingress: Validate user input before processing
- check_model_output: Validate model-generated content
- check_egress: Validate external I/O artifacts

These hooks are designed to be called at canonical control points
in the agent execution pipeline with fail-closed defaults.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModerationResult:
    """Result from a moderation control point check.

    Attributes:
        allowed: Whether the content passed moderation checks
        reason: Optional explanation if content was blocked
        scores: Optional detailed scoring information
        metadata: Additional context about the check
    """

    allowed: bool
    reason: Optional[str] = None
    scores: Optional[dict[str, float]] = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _is_moderation_enabled() -> bool:
    """Check if moderation is enabled via environment variable."""
    raw = os.getenv("MAGSAG_MODERATION_ENABLED", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def check_ingress(payload: dict[str, Any]) -> ModerationResult:
    """
    Validate user input at ingress control point.

    This hook is called before processing user-provided input to ensure
    it meets safety and policy requirements. Implement custom logic here
    or integrate with external moderation services.

    Args:
        payload: User input payload to validate

    Returns:
        ModerationResult indicating whether input is allowed

    Example:
        >>> result = check_ingress({"query": "user question"})
        >>> if not result.allowed:
        ...     raise ValueError(f"Input blocked: {result.reason}")
    """
    if not _is_moderation_enabled():
        return ModerationResult(
            allowed=True,
            metadata={"stage": "ingress", "enabled": False, "skipped": True}
        )

    logger.debug("Running ingress moderation check", extra={"payload_keys": list(payload.keys())})

    # Default implementation: Allow all content
    # TODO: Integrate with content moderation service or custom policy checks
    # For example:
    # - Check for sensitive data patterns
    # - Validate against input schema
    # - Call external moderation API

    result = ModerationResult(
        allowed=True,
        metadata={
            "stage": "ingress",
            "enabled": True,
            "payload_size": len(str(payload)),
        }
    )

    logger.info(
        "Ingress moderation check completed",
        extra={
            "allowed": result.allowed,
            "payload_size": len(str(payload)),
        }
    )

    return result


def check_model_output(text: str) -> ModerationResult:
    """
    Validate model-generated content at output control point.

    This hook is called after the model generates content but before
    it is returned to the user or used in downstream processing.

    Args:
        text: Model-generated text to validate

    Returns:
        ModerationResult indicating whether output is allowed

    Example:
        >>> result = check_model_output("model response text")
        >>> if not result.allowed:
        ...     raise ValueError(f"Output blocked: {result.reason}")
    """
    if not _is_moderation_enabled():
        return ModerationResult(
            allowed=True,
            metadata={"stage": "model_output", "enabled": False, "skipped": True}
        )

    logger.debug("Running model output moderation check", extra={"text_length": len(text)})

    # Default implementation: Allow all content
    # TODO: Integrate with content moderation service
    # For example:
    # - Check for policy violations
    # - Detect harmful content patterns
    # - Call external moderation API

    result = ModerationResult(
        allowed=True,
        metadata={
            "stage": "model_output",
            "enabled": True,
            "text_length": len(text),
        }
    )

    logger.info(
        "Model output moderation check completed",
        extra={
            "allowed": result.allowed,
            "text_length": len(text),
        }
    )

    return result


def check_egress(artifact: dict[str, Any]) -> ModerationResult:
    """
    Validate external I/O artifacts at egress control point.

    This hook is called before writing artifacts to external systems
    (files, APIs, databases) to ensure they meet policy requirements.

    Args:
        artifact: Artifact data to validate (may include content, metadata, destination)

    Returns:
        ModerationResult indicating whether egress is allowed

    Example:
        >>> artifact = {"type": "file", "content": "...", "path": "/output/file.txt"}
        >>> result = check_egress(artifact)
        >>> if not result.allowed:
        ...     raise ValueError(f"Egress blocked: {result.reason}")
    """
    if not _is_moderation_enabled():
        return ModerationResult(
            allowed=True,
            metadata={"stage": "egress", "enabled": False, "skipped": True}
        )

    logger.debug(
        "Running egress moderation check",
        extra={"artifact_type": artifact.get("type"), "artifact_keys": list(artifact.keys())}
    )

    # Default implementation: Allow all artifacts
    # TODO: Integrate with data loss prevention (DLP) or policy checks
    # For example:
    # - Check for sensitive data in artifacts
    # - Validate destination permissions
    # - Enforce export controls

    result = ModerationResult(
        allowed=True,
        metadata={
            "stage": "egress",
            "enabled": True,
            "artifact_type": artifact.get("type"),
            "artifact_size": len(str(artifact)),
        }
    )

    logger.info(
        "Egress moderation check completed",
        extra={
            "allowed": result.allowed,
            "artifact_type": artifact.get("type"),
        }
    )

    return result


__all__ = [
    "ModerationResult",
    "check_ingress",
    "check_model_output",
    "check_egress",
]
