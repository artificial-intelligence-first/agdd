"""Content moderation utilities using OpenAI omni-moderation-latest."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ModerationResult:
    """Result returned by :class:`ContentModerator`."""

    flagged: bool
    categories: tuple[str, ...]
    raw_response: Any | None = None
    checked: bool = False


class ModerationError(RuntimeError):
    """Raised when content fails moderation."""

    def __init__(
        self,
        *,
        stage: str,
        categories: tuple[str, ...],
        message: str,
        raw_response: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.categories = categories
        self.raw_response = raw_response
        self.checked = True


class ContentModerator:
    """OpenAI-powered content moderator with optional lazy client creation."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "omni-moderation-latest",
        enabled: bool | None = None,
        client: OpenAI | None = None,
    ) -> None:
        env_flag = os.getenv("AGDD_MODERATION_ENABLED")
        if enabled is None and env_flag is not None:
            enabled = env_flag.lower() != "false"
        self.enabled = True if enabled is None else enabled

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.model = model
        self._client: OpenAI | None = client
        self._lock = threading.Lock()

        if self._client is None and not self.api_key:
            if self.enabled:
                logger.info("Content moderation disabled because OPENAI_API_KEY is not configured.")
            self.enabled = False

    def bind_client(self, client: OpenAI) -> None:
        """Bind an OpenAI client instance for reuse."""
        with self._lock:
            self._client = client

    def review_texts(
        self,
        texts: Iterable[str],
        *,
        stage: str,
        actor: str | None = None,
        metadata: dict[str, Any] | None = None,
        client: OpenAI | None = None,
    ) -> ModerationResult:
        """Run moderation over concatenated texts."""
        if not self.enabled:
            return ModerationResult(False, tuple(), None, checked=False)

        combined = self._combine_texts(texts)
        if not combined:
            return ModerationResult(False, tuple(), None, checked=False)

        client_obj = client or self._ensure_client()
        if client_obj is None:
            return ModerationResult(False, tuple(), None, checked=False)

        response = client_obj.moderations.create(model=self.model, input=combined)
        categories = self._extract_flagged_categories(response)
        if categories:
            message = self._format_violation_message(stage, categories, actor, metadata)
            raise ModerationError(
                stage=stage,
                categories=tuple(sorted(categories)),
                message=message,
                raw_response=response,
            )

        return ModerationResult(False, tuple(), response, checked=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_client(self) -> OpenAI | None:
        if self._client is not None:
            return self._client
        if not self.api_key:
            return None
        with self._lock:
            if self._client is None:
                self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    @staticmethod
    def _combine_texts(texts: Iterable[str]) -> str:
        parts = [part.strip() for part in texts if isinstance(part, str) and part.strip()]
        return "\n\n".join(parts)

    @staticmethod
    def _extract_flagged_categories(response: Any) -> set[str]:
        categories: set[str] = set()
        results = getattr(response, "results", None)
        if not results:
            return categories
        for item in results:
            flagged = getattr(item, "flagged", False)
            if not flagged and not isinstance(flagged, bool):
                flagged = bool(flagged)
            if not flagged:
                continue
            raw_categories = getattr(item, "categories", None)
            if isinstance(raw_categories, dict):
                for name, value in raw_categories.items():
                    if bool(value):
                        categories.add(str(name))
        return categories

    @staticmethod
    def _format_violation_message(
        stage: str,
        categories: set[str],
        actor: str | None,
        metadata: Optional[dict[str, Any]],
    ) -> str:
        components = [f"Content moderation blocked {stage} content"]
        if actor:
            components.append(f"actor={actor}")
        if metadata:
            formatted = ", ".join(f"{k}={v}" for k, v in sorted(metadata.items()))
            if formatted:
                components.append(formatted)
        if categories:
            components.append("categories=" + ",".join(sorted(categories)))
        return "; ".join(components)


def result_to_metadata(result: ModerationResult, stage: str) -> dict[str, Any]:
    """Convert a moderation result into serializable metadata."""
    status = "skipped"
    if result.checked:
        status = "blocked" if result.flagged else "pass"
    return {
        "stage": stage,
        "status": status,
        "categories": list(result.categories),
    }


_moderator: ContentModerator | None = None
_moderator_lock = threading.Lock()


def get_content_moderator() -> ContentModerator:
    """Return a singleton content moderator instance."""
    global _moderator
    if _moderator is None:
        with _moderator_lock:
            if _moderator is None:
                _moderator = ContentModerator()
    return _moderator


def set_content_moderator(moderator: ContentModerator | None) -> None:
    """Override the global moderator (primarily for testing)."""
    global _moderator
    with _moderator_lock:
        _moderator = moderator
