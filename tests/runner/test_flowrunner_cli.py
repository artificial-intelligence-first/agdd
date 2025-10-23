from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("flow_runner", reason="flow_runner package not installed")

pytestmark = pytest.mark.skipif(shutil.which("flowctl") is None, reason="flowctl not installed")

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "flowrunner" / "prompt_flow.yaml"


def _maybe_set_pythonpath() -> None:
    """Set FLOW_RUNNER_PYTHONPATH when editable installs are in use."""
    components: list[str] = []
    for entry in sys.path:
        candidate = Path(entry)
        if not candidate.exists() or candidate.name != "site-packages":
            continue
        for pth in candidate.glob("__editable__.flowrunner-*.pth"):
            try:
                components.append(pth.read_text(encoding="utf-8").strip())
            except OSError:
                pass
        for pth in candidate.glob("__editable__.mcprouter-*.pth"):
            try:
                components.append(pth.read_text(encoding="utf-8").strip())
            except OSError:
                pass

    if components:
        os.environ.setdefault("FLOW_RUNNER_PYTHONPATH", os.pathsep.join(components))


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    _maybe_set_pythonpath()
    return subprocess.run(
        [sys.executable, "-m", "agdd.cli", *args], capture_output=True, text=True, check=False
    )


def test_flow_available_reports_status() -> None:
    cp = _run_cli("flow", "available")
    assert cp.returncode == 0
    output = cp.stdout.strip()
    assert output == "no" or output.startswith("yes")


def test_flow_validate_example_succeeds() -> None:
    assert EXAMPLE.exists()
    cp = _run_cli("flow", "validate", str(EXAMPLE))
    assert cp.returncode == 0


def test_flow_validate_with_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    # ensure schema flag propagates by pointing to existing contract file
    schema = ROOT / "catalog" / "contracts" / "flow.schema.json"
    assert schema.exists()
    cp = _run_cli("flow", "validate", str(EXAMPLE), "--schema", str(schema))
    assert cp.returncode in {0, 1}


def test_flow_run_dry_mode_succeeds() -> None:
    cp = _run_cli("flow", "run", str(EXAMPLE), "--dry-run")
    assert cp.returncode == 0
