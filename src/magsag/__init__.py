"""Core package for the MAGSAG framework."""

from __future__ import annotations

from importlib import metadata

__all__ = ("__version__",)


def _detect_version() -> str:
    """Return the installed package version or a placeholder during development."""
    try:
        return metadata.version("magsag")
    except metadata.PackageNotFoundError:
        return "0.0.0"


__version__ = _detect_version()
