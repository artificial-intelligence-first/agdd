"""Test harness customizations for the AGDD repo."""

from __future__ import annotations

import os
from pathlib import Path

_BIN_DIR = Path(__file__).resolve().parent / "bin"

if _BIN_DIR.is_dir():
    current = os.environ.get("PATH", "")
    bin_path = str(_BIN_DIR)
    parts = [segment for segment in current.split(os.pathsep) if segment]
    if bin_path not in parts:
        os.environ["PATH"] = os.pathsep.join([bin_path, *parts])
