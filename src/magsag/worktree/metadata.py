"""Persistent metadata stored alongside each worktree."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

METADATA_FILENAME = ".magsag-worktree.json"


@dataclass(slots=True)
class WorktreeMetadata:
    """Describes MAGSAG-specific attributes for a worktree."""

    run_id: str
    task: str
    base: str
    short_sha: str
    branch: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    detach: bool = False
    no_checkout: bool = False

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-serializable payload."""
        return {
            "run_id": self.run_id,
            "task": self.task,
            "base": self.base,
            "branch": self.branch,
            "short_sha": self.short_sha,
            "created_at": self.created_at.isoformat(),
            "detach": self.detach,
            "no_checkout": self.no_checkout,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "WorktreeMetadata":
        """Create metadata from stored payload."""
        created_raw = payload.get("created_at")
        created_at = None
        if isinstance(created_raw, str):
            try:
                created_at = datetime.fromisoformat(created_raw)
            except ValueError:
                created_at = datetime.now(timezone.utc)
        if created_at is None:
            created_at = datetime.now(timezone.utc)

        return cls(
            run_id=str(payload.get("run_id", "")),
            task=str(payload.get("task", "")),
            base=str(payload.get("base", "")),
            branch=payload.get("branch"),
            short_sha=str(payload.get("short_sha", "")),
            created_at=created_at,
            detach=bool(payload.get("detach", False)),
            no_checkout=bool(payload.get("no_checkout", False)),
        )


def metadata_path(worktree_path: Path) -> Path:
    """Return metadata file path under given worktree."""
    return worktree_path / METADATA_FILENAME


def load_metadata(worktree_path: Path) -> WorktreeMetadata | None:
    """Load metadata for a worktree if present."""
    path = metadata_path(worktree_path)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return WorktreeMetadata.from_payload(payload)


def write_metadata(worktree_path: Path, meta: WorktreeMetadata) -> None:
    """Persist worktree metadata."""
    path = metadata_path(worktree_path)
    worktree_path.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta.to_payload(), indent=2, ensure_ascii=True), encoding="utf-8")
