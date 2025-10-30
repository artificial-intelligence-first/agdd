"""Flow Runner adapter that conforms to the AGDD runner protocol."""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404 - subprocess required for external flowctl CLI
from importlib import metadata
from pathlib import Path
from typing import Mapping, Optional

from .base import Runner, RunnerInfo, RunResult, ValidationResult

# Default timeout for flowctl subprocess execution (5 minutes)
FLOWRUNNER_TIMEOUT_SECONDS = 300


class FlowRunner(Runner):
    """Adapter around the external `flowctl` CLI."""

    def __init__(self, exe: str = "flowctl") -> None:
        self.exe = exe

    def _resolve_executable(self) -> Optional[str]:
        """Locate the Flow Runner executable, falling back to the repo stub."""
        discovered = shutil.which(self.exe)
        if discovered:
            return discovered

        # Try local stub within the repository (bin/flowctl)
        repo_root = Path(__file__).resolve().parents[3]
        candidate = repo_root / "bin" / self.exe
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
        return None

    def is_available(self) -> bool:
        return self._resolve_executable() is not None

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
        try:
            return subprocess.run(  # nosec B603 - arguments derived from trusted executable path and flags
                args,
                capture_output=True,
                text=True,
                env=merged_env,
                timeout=FLOWRUNNER_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            return subprocess.CompletedProcess(
                args=args,
                returncode=1,
                stdout="",
                stderr=f"Process timeout after {FLOWRUNNER_TIMEOUT_SECONDS}s: {exc}",
            )
        except FileNotFoundError as exc:
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr=f"Executable not found: {exc}"
            )

    def validate(self, flow_path: Path, schema: Optional[Path] = None) -> ValidationResult:
        exe_path = self._resolve_executable()
        if exe_path is None:
            return ValidationResult(
                ok=False, stderr="flowctl is not installed. See Flow Runner setup instructions."
            )

        if schema is not None:
            args = [exe_path, "validate", str(flow_path), "--schema", str(schema)]
        else:
            args = [
                exe_path,
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
        exe_path = self._resolve_executable()
        if exe_path is None:
            return RunResult(
                ok=False, stderr="flowctl is not installed. See Flow Runner setup instructions."
            )

        args = [exe_path, "run", str(flow_path)]
        if dry_run:
            args.append("--dry-run")
        if only:
            args.extend(["--only", only])
        if continue_from:
            args.extend(["--continue-from", continue_from])

        cp = self._popen(args, env=env)
        return RunResult(ok=cp.returncode == 0, stdout=cp.stdout, stderr=cp.stderr)
