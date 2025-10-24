"""Tests for moderation utilities."""

from __future__ import annotations

import pytest

from agdd.security import (
    ModerationDecision,
    ModerationError,
    ensure_content_safe,
    render_content_for_moderation,
)


class StubModerationClient:
    """Stub moderation client for unit tests."""

    def __init__(self, decision: ModerationDecision) -> None:
        self.decision = decision
        self.seen_inputs: list[str] = []

    def moderate_text(self, text: str) -> ModerationDecision:
        self.seen_inputs.append(text)
        return self.decision


def test_render_content_for_moderation_handles_nested_structures() -> None:
    payload = {
        "title": "Hello",
        "body": ["Line one", b"Line two"],
        "metadata": {"id": 123, "tags": ["a", "b"]},
    }
    rendered = render_content_for_moderation(payload)
    assert "Hello" in rendered
    assert "Line one" in rendered
    assert "Line two" in rendered
    assert "123" in rendered
    assert "tags" in rendered


def test_ensure_content_safe_passes_when_not_flagged() -> None:
    decision = ModerationDecision(
        flagged=False,
        categories={"self-harm": False},
        category_scores={"self-harm": 0.01},
        raw={},
    )
    client = StubModerationClient(decision)

    result = ensure_content_safe("safe text", stage="input", client=client)

    assert result is decision
    assert client.seen_inputs == ["safe text"]


def test_ensure_content_safe_raises_when_flagged() -> None:
    decision = ModerationDecision(
        flagged=True,
        categories={"violence": True},
        category_scores={"violence": 0.9},
        raw={},
    )
    client = StubModerationClient(decision)

    with pytest.raises(ModerationError):
        ensure_content_safe("unsafe", stage="output", client=client)

    assert client.seen_inputs == ["unsafe"]
