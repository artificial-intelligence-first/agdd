"""Content moderation helpers using OpenAI's omni-moderation-latest model."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency safeguard
    OpenAI = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ModerationResult:
    """Result of a moderation request."""

    flagged: bool
    categories: Dict[str, bool]
    scores: Dict[str, float]
    input_text: str
    raw: Any | None = None
    skipped: bool = False


class ModerationViolationError(RuntimeError):
    """Raised when content violates moderation policy."""

    def __init__(self, message: str, *, result: ModerationResult) -> None:
        super().__init__(message)
        self.result = result


class ContentModerator:
    """Wraps the OpenAI moderation endpoint with safe fallbacks."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "omni-moderation-latest",
        enabled: Optional[bool] = None,
    ) -> None:
        self.model = model
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client: OpenAI | None = None
        self.enabled = enabled if enabled is not None else bool(self._api_key)

        if not self.enabled:
            return

        if OpenAI is None:
            logger.warning("OpenAI SDK is unavailable; disabling moderation support.")
            self.enabled = False
            return

        try:
            self._client = OpenAI(api_key=self._api_key)
        except Exception as exc:  # pragma: no cover - defensive path
            logger.warning("Failed to initialize OpenAI client for moderation: %s", exc)
            self.enabled = False

    def moderate(
        self,
        text: str,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> ModerationResult:
        """Moderate text content and return the result."""

        if not text.strip():
            return ModerationResult(
                flagged=False,
                categories={},
                scores={},
                input_text=text,
                skipped=True,
            )

        if not self.enabled or self._client is None:
            return ModerationResult(
                flagged=False,
                categories={},
                scores={},
                input_text=text,
                skipped=True,
            )

        metadata: Dict[str, Any] = {}
        if context:
            try:
                metadata = json.loads(json.dumps(context, ensure_ascii=False))
            except (TypeError, ValueError):  # pragma: no cover - context fallback
                metadata = {"context": str(context)}

        try:
            response = self._client.moderations.create(
                model=self.model,
                input=text,
                metadata=metadata or None,
            )
        except Exception as exc:  # pragma: no cover - API failure path
            logger.warning("Moderation request failed: %s", exc)
            return ModerationResult(
                flagged=False,
                categories={},
                scores={},
                input_text=text,
                skipped=True,
            )

        first_result = None
        if hasattr(response, "results"):
            results = getattr(response, "results")
            if results:
                first_result = results[0]

        if first_result is None:
            logger.debug("Moderation response missing results; treating as skipped.")
            return ModerationResult(
                flagged=False,
                categories={},
                scores={},
                input_text=text,
                raw=response,
                skipped=True,
            )

        categories = {}
        raw_categories = getattr(first_result, "categories", {})
        if isinstance(raw_categories, dict):
            categories = {k: bool(v) for k, v in raw_categories.items()}

        scores = {}
        raw_scores = getattr(first_result, "category_scores", {})
        if isinstance(raw_scores, dict):
            scores = {k: float(v) for k, v in raw_scores.items()}

        flagged = bool(getattr(first_result, "flagged", False))

        return ModerationResult(
            flagged=flagged,
            categories=categories,
            scores=scores,
            input_text=text,
            raw=response,
            skipped=False,
        )


_moderator: ContentModerator | None = None


def get_content_moderator() -> ContentModerator | None:
    """Return a singleton ContentModerator instance."""

    global _moderator
    if _moderator is None:
        _moderator = ContentModerator()
    return _moderator

