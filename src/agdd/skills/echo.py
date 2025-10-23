"""Minimal echo skill used by the walking skeleton."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Echo:
    """Return the provided text unchanged."""

    def __call__(self, text: str) -> str:
        return text


__all__ = ["Echo"]
