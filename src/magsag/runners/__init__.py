"""Runner interfaces and adapters for MAGSAG."""

from __future__ import annotations

from .base import Runner, RunnerInfo, RunResult, ValidationResult
from .flowrunner import FlowRunner

__all__ = ["Runner", "RunnerInfo", "ValidationResult", "RunResult", "FlowRunner"]
