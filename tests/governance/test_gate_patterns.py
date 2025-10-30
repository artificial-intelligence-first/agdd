"""Tests for governance gate pattern matching."""

from __future__ import annotations

from agdd.governance.gate import _match_pattern


def test_match_pattern_exact() -> None:
    """Test exact pattern matching."""
    assert _match_pattern("gpt-4", "gpt-4")
    assert not _match_pattern("gpt-4", "gpt-3")


def test_match_pattern_wildcard_suffix() -> None:
    """Test wildcard pattern matching with suffix."""
    assert _match_pattern("internal-experimental-v1", "internal-experimental-*")
    assert _match_pattern("internal-experimental-v2", "internal-experimental-*")
    assert not _match_pattern("public-model", "internal-experimental-*")


def test_match_pattern_wildcard_prefix() -> None:
    """Test wildcard pattern matching with prefix."""
    assert _match_pattern("v1-experimental", "*-experimental")
    assert _match_pattern("v2-experimental", "*-experimental")
    assert not _match_pattern("experimental-v1", "*-experimental")


def test_match_pattern_wildcard_middle() -> None:
    """Test wildcard pattern matching in the middle."""
    assert _match_pattern("model-v1-experimental", "model-*-experimental")
    assert _match_pattern("model-v2-experimental", "model-*-experimental")
    assert not _match_pattern("model-experimental", "model-*-experimental")
