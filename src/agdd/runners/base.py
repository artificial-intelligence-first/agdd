"""Runner abstraction for orchestrating flows in AGDD."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Optional, Protocol, Set

RunnerCapability = Literal["dry-run", "resume", "retries", "artifacts", "otel-trace", "ui"]


@dataclass(slots=True)
class ValidationResult:
    """Outcome of validating a flow definition."""

    ok: bool
    stdout: str = ""
    stderr: str = ""


@dataclass(slots=True)
class RunResult:
    """Outcome of executing a flow."""

    ok: bool
    stdout: str = ""
    stderr: str = ""


@dataclass(slots=True)
class RunnerInfo:
    """Metadata describing a runner implementation."""

    name: str
    version: str
    capabilities: Set[RunnerCapability]


class Runner(Protocol):
    """Protocol describing the runner surface expected by AGDD."""

    def is_available(self) -> bool:  # pragma: no cover - interface contract
        """Return True when the runner can be used on this system."""

    def info(self) -> RunnerInfo:  # pragma: no cover - interface contract
        """Return metadata and capability information for the runner."""

    def validate(
        self, flow_path: Path, schema: Optional[Path] = None
    ) -> ValidationResult:  # pragma: no cover - interface contract
        """Validate a flow definition against optional schema hints."""

    def run(
        self,
        flow_path: Path,
        *,
        dry_run: bool = False,
        only: Optional[str] = None,
        continue_from: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> RunResult:  # pragma: no cover - interface contract
        """Execute the provided flow definition with optional constraints."""
