"""Skill registry for the AGDD walking skeleton."""
from __future__ import annotations

from typing import Callable, Dict, Iterable, Protocol

from .echo import Echo

SkillFactory = Callable[[], "Skill"]


class Skill(Protocol):
    """Callable protocol for simple text-in/text-out skills."""

    def __call__(self, text: str) -> str:  # pragma: no cover - signature only
        ...


_SKILL_FACTORIES: Dict[str, SkillFactory] = {
    "echo": Echo,
}


def available_skills() -> Iterable[str]:
    """Return the identifiers of registered skills."""
    return _SKILL_FACTORIES.keys()


def get_skill(name: str) -> Skill:
    """Instantiate a registered skill by name."""
    try:
        factory = _SKILL_FACTORIES[name]
    except KeyError as exc:  # pragma: no cover - tiny helper
        raise KeyError(name) from exc
    return factory()


__all__ = ["Skill", "SkillFactory", "available_skills", "get_skill"]
