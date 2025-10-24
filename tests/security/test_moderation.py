from __future__ import annotations

from types import SimpleNamespace

import pytest

from agdd.security.moderation import (
    ContentModerator,
    ModerationError,
    get_content_moderator,
    result_to_metadata,
    set_content_moderator,
)


class DummyModerations:
    def __init__(self, flagged: bool, categories: dict[str, bool] | None = None) -> None:
        self._flagged = flagged
        self._categories = categories or {}

    def create(self, *, model: str, input: str) -> SimpleNamespace:
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    flagged=self._flagged,
                    categories=self._categories,
                )
            ]
        )


class DummyClient:
    def __init__(self, flagged: bool, categories: dict[str, bool] | None = None) -> None:
        self.moderations = DummyModerations(flagged=flagged, categories=categories)


def test_review_texts_disabled_without_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    moderator = ContentModerator(enabled=True, client=None, api_key=None)
    result = moderator.review_texts(["hello"], stage="input")
    assert not result.checked
    assert not result.flagged
    assert result.categories == ()


def test_review_texts_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = DummyClient(flagged=False)
    moderator = ContentModerator(client=client)
    result = moderator.review_texts(["hello"], stage="input")
    assert result.checked
    assert not result.flagged
    assert result.categories == ()
    metadata = result_to_metadata(result, "input")
    assert metadata["status"] == "pass"
    assert metadata["categories"] == []


def test_review_texts_block(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    categories = {"violence": True, "self-harm": False}
    client = DummyClient(flagged=True, categories=categories)
    moderator = ContentModerator(client=client)
    with pytest.raises(ModerationError) as excinfo:
        moderator.review_texts(["unsafe"], stage="output", metadata={"provider": "test"})
    error = excinfo.value
    assert error.stage == "output"
    assert "provider=test" in str(error)
    assert "violence" in ",".join(error.categories)


def test_get_and_set_content_moderator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    set_content_moderator(None)
    custom = ContentModerator(enabled=False)
    set_content_moderator(custom)
    assert get_content_moderator() is custom
    set_content_moderator(None)
