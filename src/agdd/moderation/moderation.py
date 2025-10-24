"""
OpenAI Content Moderation (omni-moderation-latest).

This module provides content moderation before and after LLM interactions
using OpenAI's omni-moderation-latest model to ensure safe content generation.

Reference: https://platform.openai.com/docs/guides/moderation
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


class ModerationCategory(str, Enum):
    """Moderation categories from OpenAI moderation API."""

    HARASSMENT = "harassment"
    HARASSMENT_THREATENING = "harassment/threatening"
    HATE = "hate"
    HATE_THREATENING = "hate/threatening"
    ILLICIT = "illicit"
    ILLICIT_VIOLENT = "illicit/violent"
    SELF_HARM = "self-harm"
    SELF_HARM_INTENT = "self-harm/intent"
    SELF_HARM_INSTRUCTIONS = "self-harm/instructions"
    SEXUAL = "sexual"
    SEXUAL_MINORS = "sexual/minors"
    VIOLENCE = "violence"
    VIOLENCE_GRAPHIC = "violence/graphic"


@dataclass(slots=True)
class ModerationResult:
    """Result from content moderation check."""

    flagged: bool
    categories: dict[str, bool] = field(default_factory=dict)
    category_scores: dict[str, float] = field(default_factory=dict)
    category_applied_input_types: dict[str, list[str]] = field(default_factory=dict)
    model: str = "omni-moderation-latest"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def flagged_categories(self) -> list[str]:
        """Get list of flagged category names."""
        return [cat for cat, flagged in self.categories.items() if flagged]

    @property
    def highest_risk_category(self) -> tuple[str, float] | None:
        """Get the category with the highest risk score."""
        if not self.category_scores:
            return None
        max_category = max(self.category_scores.items(), key=lambda x: x[1])
        return max_category


@dataclass(slots=True)
class ModerationConfig:
    """Configuration for moderation service."""

    api_key: Optional[str] = None
    model: str = "omni-moderation-latest"
    enable_input_moderation: bool = True
    enable_output_moderation: bool = True
    block_on_flagged: bool = True
    fail_closed_on_error: bool = False  # If True, treat API errors as flagged content
    timeout: float = 10.0

    def get_api_key(self) -> str:
        """Get API key from config or environment."""
        if self.api_key:
            return self.api_key
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            msg = "OPENAI_API_KEY not found in config or environment"
            raise ValueError(msg)
        return key


class ModerationError(Exception):
    """Raised when content is flagged by moderation."""

    def __init__(self, message: str, result: ModerationResult):
        super().__init__(message)
        self.result = result


class ModerationService:
    """
    Content moderation service using OpenAI omni-moderation API.

    Provides input and output content moderation to ensure safe interactions.
    """

    def __init__(self, config: Optional[ModerationConfig] = None):
        """
        Initialize moderation service.

        Args:
            config: Moderation configuration (uses defaults if None)
        """
        self.config = config or ModerationConfig()
        self.client = OpenAI(
            api_key=self.config.get_api_key(),
            timeout=self.config.timeout,
        )

    def moderate(
        self,
        content: str,
        *,
        multimodal_input: Optional[list[dict[str, Any]]] = None,
    ) -> ModerationResult:
        """
        Check content for policy violations.

        Args:
            content: Text content to moderate
            multimodal_input: Optional multimodal content (images, etc.)
                            Format: [{"type": "image_url", "image_url": {...}}]

        Returns:
            ModerationResult with flagged categories and scores

        Raises:
            httpx.HTTPError: On API errors
        """
        # Build moderation request
        # Note: For omni-moderation-latest, multimodal format must match OpenAI spec:
        # Text-only: string
        # Multimodal: array with proper content type schemas
        input_data: Any  # Type varies: str for text-only, list for multimodal

        if multimodal_input:
            # Multimodal moderation - build content array
            # For images, multimodal_input should be: [{"type": "image_url", "image_url": {...}}]

            # Only include text if non-empty
            if content and content.strip():
                input_data = [{"type": "text", "text": content}]
                input_data.extend(multimodal_input)
            else:
                # Image-only moderation
                input_data = multimodal_input
        else:
            # Text-only moderation
            input_data = content

        try:
            response = self.client.moderations.create(
                model=self.config.model,
                input=input_data,
            )

            # Parse first result (batch moderation returns list)
            result = response.results[0]

            return ModerationResult(
                flagged=result.flagged,
                categories={cat: val for cat, val in result.categories.model_dump().items()},
                category_scores={
                    cat: score for cat, score in result.category_scores.model_dump().items()
                },
                category_applied_input_types=getattr(
                    result, "category_applied_input_types", {}
                ),
                model=self.config.model,
                metadata={
                    "content_length": len(content),
                    "has_multimodal": bool(multimodal_input),
                },
            )
        except Exception as e:
            # Log the full error for debugging
            logger.error(
                f"Moderation API error: {e}",
                exc_info=True,
                extra={
                    "model": self.config.model,
                    "has_multimodal": bool(multimodal_input),
                    "content_length": len(content),
                },
            )

            # Error handling strategy depends on configuration
            # fail_closed_on_error=True: Treat errors as policy violations (safer)
            # fail_closed_on_error=False: Treat errors as permissive (avoid false positives)
            if self.config.fail_closed_on_error:
                logger.warning(
                    "Moderation API error in fail-closed mode - flagging content as unsafe"
                )
                return ModerationResult(
                    flagged=True,
                    categories={"moderation_error": True},
                    metadata={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "fail_closed": True,
                    },
                )
            else:
                # Permissive fallback to avoid blocking legitimate content
                return ModerationResult(
                    flagged=False,
                    metadata={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "fallback": True,
                    },
                )

    def moderate_input(self, content: str) -> ModerationResult:
        """
        Moderate user input before sending to LLM.

        Args:
            content: User input to moderate

        Returns:
            ModerationResult

        Raises:
            ModerationError: If content is flagged and block_on_flagged=True
        """
        if not self.config.enable_input_moderation:
            return ModerationResult(flagged=False, metadata={"skipped": True})

        result = self.moderate(content)

        if result.flagged and self.config.block_on_flagged:
            flagged_cats = ", ".join(result.flagged_categories)
            msg = f"Input content flagged for policy violations: {flagged_cats}"
            raise ModerationError(msg, result)

        return result

    def moderate_output(self, content: str) -> ModerationResult:
        """
        Moderate LLM output before returning to user.

        Args:
            content: LLM output to moderate

        Returns:
            ModerationResult

        Raises:
            ModerationError: If content is flagged and block_on_flagged=True
        """
        if not self.config.enable_output_moderation:
            return ModerationResult(flagged=False, metadata={"skipped": True})

        result = self.moderate(content)

        if result.flagged and self.config.block_on_flagged:
            flagged_cats = ", ".join(result.flagged_categories)
            msg = f"Output content flagged for policy violations: {flagged_cats}"
            raise ModerationError(msg, result)

        return result

    def batch_moderate(self, contents: list[str]) -> list[ModerationResult]:
        """
        Moderate multiple content items in a single API call.

        Args:
            contents: List of content strings to moderate

        Returns:
            List of ModerationResults (one per input)
        """
        if not contents:
            return []

        try:
            response = self.client.moderations.create(
                model=self.config.model,
                input=contents,
            )

            results = []
            for result in response.results:
                results.append(
                    ModerationResult(
                        flagged=result.flagged,
                        categories={
                            cat: val for cat, val in result.categories.model_dump().items()
                        },
                        category_scores={
                            cat: score
                            for cat, score in result.category_scores.model_dump().items()
                        },
                        category_applied_input_types=getattr(
                            result, "category_applied_input_types", {}
                        ),
                        model=self.config.model,
                    )
                )

            return results
        except Exception as e:
            # Log the full error for debugging
            logger.error(
                f"Batch moderation API error: {e}",
                exc_info=True,
                extra={
                    "model": self.config.model,
                    "batch_size": len(contents),
                },
            )

            # Error handling strategy depends on configuration
            # fail_closed_on_error=True: Treat errors as policy violations (safer)
            # fail_closed_on_error=False: Treat errors as permissive (avoid false positives)
            if self.config.fail_closed_on_error:
                logger.warning(
                    f"Batch moderation API error in fail-closed mode - flagging all {len(contents)} items as unsafe"
                )
                return [
                    ModerationResult(
                        flagged=True,
                        categories={"moderation_error": True},
                        metadata={
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "fail_closed": True,
                            "batch_index": i,
                        },
                    )
                    for i in range(len(contents))
                ]
            else:
                # Permissive fallback to avoid blocking legitimate content
                return [
                    ModerationResult(
                        flagged=False,
                        metadata={
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "fallback": True,
                            "batch_index": i,
                        },
                    )
                    for i in range(len(contents))
                ]


# Global singleton instance
_service: Optional[ModerationService] = None


def get_moderation_service(config: Optional[ModerationConfig] = None) -> ModerationService:
    """Get or create global moderation service instance."""
    global _service
    if _service is None:
        _service = ModerationService(config)
    return _service


def moderate_content(
    content: str,
    *,
    check_input: bool = True,
    check_output: bool = False,
    config: Optional[ModerationConfig] = None,
) -> ModerationResult:
    """
    Convenience function to moderate content.

    Args:
        content: Content to moderate
        check_input: If True, use input moderation rules
        check_output: If True, use output moderation rules
        config: Optional configuration

    Returns:
        ModerationResult

    Raises:
        ModerationError: If content is flagged and blocking is enabled
    """
    service = get_moderation_service(config)

    if check_input:
        return service.moderate_input(content)
    elif check_output:
        return service.moderate_output(content)
    else:
        return service.moderate(content)
