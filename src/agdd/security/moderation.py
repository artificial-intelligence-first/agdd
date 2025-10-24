"""OpenAI moderation integration for AGDD."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Mapping, Sequence

from openai import OpenAI

logger = logging.getLogger(__name__)

_MAX_MODERATION_CHARS = 20_000


class ModerationError(RuntimeError):
    """Raised when moderation flags unsafe content."""


@dataclass(frozen=True)
class ModerationDecision:
    """Represents the result of a moderation check."""

    flagged: bool
    categories: dict[str, bool]
    category_scores: dict[str, float]
    raw: dict[str, Any]


class ModerationClient:
    """Thin wrapper around OpenAI's moderation endpoint."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        resolved_key = api_key or os.getenv("OPENAI_MODERATION_API_KEY") or os.getenv(
            "OPENAI_API_KEY"
        )
        if not resolved_key:
            raise RuntimeError(
                "OpenAI moderation requires OPENAI_API_KEY or OPENAI_MODERATION_API_KEY"
            )
        self._client = OpenAI(api_key=resolved_key)
        self.model = model or os.getenv("OPENAI_MODERATION_MODEL", "omni-moderation-latest")

    def moderate_text(self, text: str) -> ModerationDecision:
        """Run moderation on text and return the decision."""

        trimmed = text[:_MAX_MODERATION_CHARS]
        response = self._client.moderations.create(model=self.model, input=trimmed)
        results: Iterable[Any] = getattr(response, "results", [])
        first = next(iter(results), None)
        if first is None:
            raise RuntimeError("OpenAI moderation returned no results")

        categories_raw = getattr(first, "categories", {})
        scores_raw = getattr(first, "category_scores", {})
        decision = ModerationDecision(
            flagged=bool(getattr(first, "flagged", False)),
            categories={str(k): bool(v) for k, v in dict(categories_raw).items()},
            category_scores={str(k): float(v) for k, v in dict(scores_raw).items()},
            raw=_safe_model_dump(first),
        )
        return decision


def _safe_model_dump(obj: Any) -> dict[str, Any]:
    """Best-effort conversion of an OpenAI object to a JSON-serializable dict."""

    if hasattr(obj, "model_dump"):
        dumped = obj.model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    if hasattr(obj, "dict"):
        dumped = obj.dict()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    try:
        return json.loads(json.dumps(obj, default=str))
    except Exception:  # noqa: BLE001
        return {"repr": repr(obj)}


def render_content_for_moderation(content: Any) -> str:
    """Flatten complex payloads into a single string for moderation."""

    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="ignore")
    if isinstance(content, Mapping):
        return json.dumps(_normalize_mapping(content), ensure_ascii=False)
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        parts = [render_content_for_moderation(item) for item in content]
        return "\n".join(part for part in parts if part)
    return str(content)


def _normalize_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively convert mapping values to moderation-safe primitives."""

    normalized: dict[str, Any] = {}
    for key, value in mapping.items():
        normalized[str(key)] = _normalize_value(value)
    return normalized


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _normalize_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value


@lru_cache(maxsize=1)
def get_moderation_client() -> ModerationClient:
    """Get a cached moderation client instance."""

    return ModerationClient()


def ensure_content_safe(
    content: Any,
    *,
    stage: str,
    client: ModerationClient | None = None,
) -> ModerationDecision | None:
    """Ensure that content passes moderation, raising if flagged."""

    text = render_content_for_moderation(content).strip()
    if not text:
        return None

    active_client = client or get_moderation_client()
    decision = active_client.moderate_text(text)
    categories = [name for name, flagged in decision.categories.items() if flagged]
    logger.debug(
        "Moderation result for stage '%s': flagged=%s categories=%s",
        stage,
        decision.flagged,
        categories,
    )
    if decision.flagged:
        message = (
            f"Moderation blocked {stage} content due to categories: {', '.join(categories) or 'unknown'}"
        )
        raise ModerationError(message)
    return decision
