"""Project-wide site customizations for the AGDD repository."""

from __future__ import annotations

import sys
from pathlib import Path


def _tests_dir() -> Path:
    return (Path(__file__).resolve().parent / "tests").resolve()


def _strip_tests_from_sys_path() -> None:
    tests_dir = _tests_dir()
    for idx, entry in reversed(list(enumerate(sys.path))):
        if not entry:
            continue
        try:
            resolved = Path(entry).resolve()
        except Exception:
            continue
        if resolved == tests_dir:
            sys.path.pop(idx)


def _reset_mcp_modules() -> None:
    for key in list(sys.modules):
        if key == "mcp" or key.startswith("mcp."):
            sys.modules.pop(key, None)


_strip_tests_from_sys_path()
_reset_mcp_modules()
