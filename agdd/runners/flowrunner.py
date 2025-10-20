"""Flow Runner adapter that conforms to the AGDD runner protocol."""
from __future__ import annotations

import os
import shutil
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Mapping, Optional

from .base import RunResult, Runner, RunnerInfo, ValidationResult


class FlowRunner(Runner):
    """Adapter around the external `flowctl` CLI."""

    def __init__(self, exe: str = "flowctl") -> None:
        self.exe = exe

    def is_available(self) -> bool:
        return shutil.which(self.exe) is not None

    def info(self) -> RunnerInfo:
        try:
            version = metadata.version("flowrunner")
        except metadata.PackageNotFoundError:
            version = "unknown"
        return RunnerInfo(
            name="flow-runner",
            version=version,
            capabilities={"dry-run", "artifacts"},
        )

    def _popen(
        self, args: list[str], env: Optional[Mapping[str, str]]
    ) -> subprocess.CompletedProcess[str]:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        custom_path = merged_env.get("FLOW_RUNNER_PYTHONPATH")
        if custom_path:
            existing = merged_env.get("PYTHONPATH")
            merged_env["PYTHONPATH"] = (
                f"{custom_path}{os.pathsep}{existing}" if existing else custom_path
            )
        return subprocess.run(args, capture_output=True, text=True, env=merged_env)

    def validate(self, flow_path: Path, schema: Optional[Path] = None) -> ValidationResult:
        if not self.is_available():
            return ValidationResult(
                ok=False, stderr="flowctl is not installed. See Flow Runner setup instructions."
            )

        if schema is not None:
            args = [self.exe, "validate", str(flow_path), "--schema", str(schema)]
        else:
            args = [
                self.exe,
                "run",
                str(flow_path),
                "--dry-run",
            ]
        cp = self._popen(args, env=None)
        ok = cp.returncode == 0

        return ValidationResult(ok=ok, stdout=cp.stdout, stderr=cp.stderr)

    def run(
        self,
        flow_path: Path,
        *,
        dry_run: bool = False,
        only: Optional[str] = None,
        continue_from: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> RunResult:
        if not self.is_available():
            return RunResult(
                ok=False, stderr="flowctl is not installed. See Flow Runner setup instructions."
            )

        args = [self.exe, "run", str(flow_path)]
        if dry_run:
            args.append("--dry-run")
        if only:
            args.extend(["--only", only])
        if continue_from:
            args.extend(["--continue-from", continue_from])

        cp = self._popen(args, env=env)
        return RunResult(ok=cp.returncode == 0, stdout=cp.stdout, stderr=cp.stderr)
