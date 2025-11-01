"""High-level orchestration for Git worktree lifecycle."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import perf_counter

from magsag.utils import find_project_root

from magsag.observability.tracing import get_meter, trace_span

from .config import WorktreeSettings, ensure_within_root, get_worktree_settings
from .exceptions import (
    GitCommandError,
    WorktreeConflictError,
    WorktreeDirtyError,
    WorktreeError,
    WorktreeForbiddenError,
    WorktreeLimitError,
    WorktreeNotFoundError,
)
from .git import parse_porcelain_z, run as git_run
from .metadata import (
    METADATA_FILENAME,
    WorktreeMetadata,
    load_metadata,
    metadata_path,
    write_metadata,
)
from .naming import branch_name, directory_name, sanitize_segment
from .types import WorktreeInfo
from .events import publish_event

PROTECTED_BRANCHES = {"main"}
PROTECTED_PREFIXES: tuple[str, ...] = ("release/",)

_metrics_lock: Lock = Lock()
_metrics_ready = False
_create_hist = None
_remove_hist = None
_active_counter = None
_active_snapshot = 0


def _normalize_base_ref(ref: str) -> str:
    """Normalize refs to bare branch names for policy checks."""
    value = ref.strip()
    if value.startswith("refs/heads/"):
        value = value[len("refs/heads/") :]
    if value.startswith("refs/remotes/"):
        value = value[len("refs/remotes/") :]
    parts = value.split("/", 1)
    if parts[0] in {"origin", "upstream"} and len(parts) == 2:
        value = parts[1]
    return value


def _is_protected_base(ref: str) -> bool:
    """Return True when the base ref points at a protected branch."""
    normalized = _normalize_base_ref(ref)
    if normalized in PROTECTED_BRANCHES:
        return True
    return any(normalized.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def _ensure_metrics() -> None:
    """Initialise meter instruments lazily."""
    global _metrics_ready, _create_hist, _remove_hist, _active_counter
    if _metrics_ready:
        return
    with _metrics_lock:
        if _metrics_ready:
            return
        try:
            meter = get_meter()
        except Exception:
            meter = None
        if meter is not None:
            try:
                _create_hist = meter.create_histogram(
                    "worktree_create_duration_ms",
                    unit="ms",
                    description="Duration to create a managed git worktree",
                )
            except Exception:
                _create_hist = None
            try:
                _remove_hist = meter.create_histogram(
                    "worktree_remove_duration_ms",
                    unit="ms",
                    description="Duration to remove a managed git worktree",
                )
            except Exception:
                _remove_hist = None
            try:
                _active_counter = meter.create_up_down_counter(
                    "worktrees_active",
                    unit="1",
                    description="Number of active managed git worktrees",
                )
            except Exception:
                _active_counter = None
        _metrics_ready = True


def _record_create_duration(duration_ms: float, attributes: dict[str, object]) -> None:
    _ensure_metrics()
    if _create_hist is None:
        return
    try:
        _create_hist.record(duration_ms, attributes=attributes)
    except Exception:
        pass


def _record_remove_duration(duration_ms: float, attributes: dict[str, object]) -> None:
    _ensure_metrics()
    if _remove_hist is None:
        return
    try:
        _remove_hist.record(duration_ms, attributes=attributes)
    except Exception:
        pass


def _set_active_count(value: int) -> None:
    _ensure_metrics()
    global _active_snapshot
    if _active_counter is None:
        _active_snapshot = value
        return
    delta = value - _active_snapshot
    if not delta:
        return
    try:
        _active_counter.add(delta)
        _active_snapshot = value
    except Exception:
        pass


def _is_metadata_entry(line: str) -> bool:
    stripped = line.strip()
    if not stripped or not stripped.startswith("??"):
        return False
    path = stripped[2:].strip()
    if path.startswith("./"):
        path = path[2:]
    return path == METADATA_FILENAME


def force_removal_allowed() -> bool:
    """Return True when the current environment is permitted to use --force."""
    flag = os.environ.get("MAGSAG_WT_ALLOW_FORCE", "")
    return flag.lower() in {"1", "true", "yes"}


@dataclass(slots=True)
class WorktreeRecord:
    """Aggregate of Git state and MAGSAG metadata for a worktree."""

    info: WorktreeInfo
    metadata: WorktreeMetadata | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable representation."""
        data: dict[str, object] = {
            "path": str(self.info.path),
            "head": self.info.head,
            "branch": self.info.branch_short,
            "detached": self.info.is_detached,
            "locked": self.info.locked,
            "lock_reason": self.info.lock_reason,
            "prunable": self.info.prunable,
            "prunable_reason": self.info.prunable_reason,
            "is_ephemeral": self.info.is_ephemeral,
        }
        if self.metadata:
            data["run_id"] = self.metadata.run_id
            data["task"] = self.metadata.task
            data["base"] = self.metadata.base
            data["short_sha"] = self.metadata.short_sha
            data["created_at"] = self.metadata.created_at.isoformat()
            data["detach"] = self.metadata.detach
            data["no_checkout"] = self.metadata.no_checkout
        else:
            data["run_id"] = self.info.run_id
            data["task"] = self.info.task_slug
        return data


class WorktreeManager:
    """Encapsulates Git worktree lifecycle management."""

    def __init__(
        self,
        settings: WorktreeSettings | None = None,
        *,
        repo_root: Path | None = None,
    ):
        self.settings = settings or get_worktree_settings()
        self.repo_root = repo_root or find_project_root()

    # ------------------------------------------------------------------
    # Listing helpers

    def list_records(self) -> list[WorktreeRecord]:
        """Return a list of worktree records including the primary checkout."""
        with trace_span(
            "git.worktree.list",
            {
                "worktree.root": str(self.settings.root),
                "worktree.repo_root": str(self.repo_root),
            },
        ) as span:
            result = git_run(
                ["worktree", "list", "--porcelain", "-z"],
                cwd=self.repo_root,
            )
            infos = parse_porcelain_z(result.stdout or b"")
            span.set_attribute("worktree.list.count", len(infos))
        records: list[WorktreeRecord] = []
        for info in infos:
            meta = None
            try:
                meta = load_metadata(info.path)
            except FileNotFoundError:
                meta = None
            records.append(WorktreeRecord(info=info, metadata=meta))
        return records

    def _filter_managed(self, records: list[WorktreeRecord]) -> list[WorktreeRecord]:
        """Filter records that live under the managed worktree root."""
        managed: list[WorktreeRecord] = []
        for record in records:
            try:
                record.info.path.resolve().relative_to(self.settings.root)
            except ValueError:
                continue
            managed.append(record)
        return managed

    def managed_records(self) -> list[WorktreeRecord]:
        """Return records that live under the managed worktree root."""
        return self._filter_managed(self.list_records())

    # ------------------------------------------------------------------
    # Creation

    def create(
        self,
        *,
        run_id: str,
        task: str,
        base: str,
        detach: bool = False,
        no_checkout: bool = False,
        lock_reason: str | None = None,
        auto_lock: bool = False,
    ) -> WorktreeRecord:
        """Create a new worktree following MAGSAG naming conventions."""
        self._enforce_concurrency_limit()
        if detach and _is_protected_base(base):
            raise WorktreeForbiddenError(
                f"Base reference {base!r} is protected when creating detached worktrees."
            )

        short_sha = self._short_sha(base)
        directory = directory_name(run_id, task, short_sha)
        worktree_path = ensure_within_root(Path(directory), self.settings.root)

        if worktree_path.exists():
            raise WorktreeConflictError(f"Worktree directory already exists: {worktree_path}")

        branch = None
        if not detach:
            branch = branch_name(run_id, task)
            self._ensure_branch_available(branch)

        args: list[str] = ["worktree", "add"]
        if detach:
            args.append("--detach")
        if no_checkout:
            args.append("--no-checkout")
        if branch:
            args.extend(["-b", branch])
        args.append(str(worktree_path))
        args.append(base)

        metadata = WorktreeMetadata(
            run_id=run_id,
            task=task,
            base=base,
            branch=branch,
            short_sha=short_sha,
            created_at=datetime.now(timezone.utc),
            detach=detach,
            no_checkout=no_checkout,
        )

        start = perf_counter()
        records: list[WorktreeRecord]
        record: WorktreeRecord
        with trace_span(
            "git.worktree.add",
            {
                "worktree.path": str(worktree_path),
                "worktree.branch": branch or "<detached>",
                "worktree.detach": detach,
                "worktree.no_checkout": no_checkout,
                "worktree.run_id": metadata.run_id,
                "worktree.task": metadata.task,
                "worktree.short_sha": metadata.short_sha,
            },
        ) as span:
            git_run(args, cwd=self.repo_root)
            write_metadata(worktree_path, metadata)
            records = self.list_records()
            record = self._record_for_path(worktree_path, records=records)
            span.set_attribute("worktree.id", record.info.path.name)
            span.set_attribute("worktree.locked", record.info.locked)

        if auto_lock or lock_reason:
            self._lock_path(
                worktree_path,
                reason=lock_reason,
                record=record,
                locked=True,
            )
            records = self.list_records()
            record = self._record_for_path(worktree_path, records=records)

        duration_ms = (perf_counter() - start) * 1000
        _record_create_duration(
            duration_ms,
            {
                "worktree.branch": record.info.branch_short or "<detached>",
                "worktree.detached": record.info.is_detached,
                "worktree.locked": record.info.locked,
            },
        )
        self._refresh_active_metric(records=records)
        publish_event("worktree.create", record.to_dict())
        if auto_lock or lock_reason:
            publish_event("worktree.lock", record.to_dict())

        return record

    # ------------------------------------------------------------------
    # Mutating operations

    def remove(self, run_id: str, *, force: bool = False) -> None:
        """Remove a worktree identified by run ID."""
        record = self._resolve_run_id(run_id)
        if record is None:
            raise WorktreeNotFoundError(f"No worktree found for run_id={run_id}")
        payload = record.to_dict()
        payload["force"] = force

        if force and not force_removal_allowed():
            raise WorktreeForbiddenError(
                "Force removal is restricted to CI maintenance role. "
                "Set MAGSAG_WT_ALLOW_FORCE=1 in trusted contexts."
            )

        if not force:
            self._ensure_clean(record.info.path)

        meta_file = metadata_path(record.info.path)
        if meta_file.exists():
            try:
                meta_file.unlink()
            except OSError:
                pass

        args: list[str] = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(record.info.path))

        start = perf_counter()
        with trace_span(
            "git.worktree.remove",
            {
                "worktree.path": str(record.info.path),
                "worktree.branch": record.info.branch_short or "<detached>",
                "worktree.force": force,
            },
        ) as span:
            span.set_attribute("worktree.id", record.info.path.name)
            span.set_attribute("worktree.locked", record.info.locked)
            if record.metadata:
                span.set_attribute("worktree.run_id", record.metadata.run_id)
                span.set_attribute("worktree.task", record.metadata.task)
                span.set_attribute("worktree.short_sha", record.metadata.short_sha)
            else:
                if record.info.run_id:
                    span.set_attribute("worktree.run_id", record.info.run_id)
                if record.info.task_slug:
                    span.set_attribute("worktree.task", record.info.task_slug)
            if record.info.head:
                span.set_attribute("worktree.head", record.info.head)
            git_run(args, cwd=self.repo_root)
        duration_ms = (perf_counter() - start) * 1000
        records = self.list_records()
        _record_remove_duration(
            duration_ms,
            {
                "worktree.branch": record.info.branch_short or "<detached>",
                "worktree.locked": record.info.locked,
                "worktree.force": force,
            },
        )
        self._refresh_active_metric(records=records)
        publish_event("worktree.remove", payload)
        try:
            self.prune()
        except WorktreeError:
            pass

    def lock(self, run_id: str, *, reason: str | None = None) -> WorktreeRecord:
        """Lock a worktree to prevent garbage collection."""
        record = self._resolve_or_raise(run_id)
        self._lock_path(record.info.path, reason=reason, record=record, locked=True)
        records = self.list_records()
        updated = self._record_for_path(record.info.path, records=records)
        publish_event("worktree.lock", updated.to_dict())
        return updated

    def unlock(self, run_id: str) -> WorktreeRecord:
        """Unlock a previously locked worktree."""
        record = self._resolve_or_raise(run_id)
        with trace_span(
            "git.worktree.unlock",
            {
                "worktree.path": str(record.info.path),
                "worktree.branch": record.info.branch_short or "<detached>",
            },
        ) as span:
            span.set_attribute("worktree.id", record.info.path.name)
            span.set_attribute("worktree.locked_before", record.info.locked)
            span.set_attribute("worktree.locked", False)
            if record.metadata:
                span.set_attribute("worktree.run_id", record.metadata.run_id)
                span.set_attribute("worktree.task", record.metadata.task)
            else:
                if record.info.run_id:
                    span.set_attribute("worktree.run_id", record.info.run_id)
                if record.info.task_slug:
                    span.set_attribute("worktree.task", record.info.task_slug)
            args = ["worktree", "unlock", str(record.info.path)]
            git_run(args, cwd=self.repo_root)
        records = self.list_records()
        updated = self._record_for_path(record.info.path, records=records)
        publish_event("worktree.unlock", updated.to_dict())
        return updated

    def prune(self, *, expire: str | None = None) -> None:
        """Prune stale worktrees based on Git metadata."""
        ttl = expire or self.settings.ttl_spec
        before_records = self.managed_records()
        before = len(before_records)
        after_records: list[WorktreeRecord]
        managed_after: list[WorktreeRecord]
        removed = 0
        after = 0
        with trace_span(
            "git.worktree.prune",
            {
                "worktree.root": str(self.settings.root),
                "worktree.expire": ttl,
            },
        ) as span:
            span.set_attribute("worktree.before_count", before)
            git_run(["worktree", "prune", f"--expire={ttl}"], cwd=self.repo_root)
            after_records = self.list_records()
            managed_after = self._filter_managed(after_records)
            after = len(managed_after)
            removed = max(0, before - after)
            span.set_attribute("worktree.after_count", after)
            span.set_attribute("worktree.removed_count", removed)
        self._refresh_active_metric(records=after_records)
        publish_event(
            "worktree.prune",
            {
                "expire": ttl,
                "before": before,
                "after": after,
                "removed": removed,
                "root": str(self.settings.root),
            },
        )

    def repair(self) -> None:
        """Repair worktree administrative files after manual moves."""
        with trace_span(
            "git.worktree.repair",
            {
                "worktree.root": str(self.settings.root),
            },
        ):
            git_run(["worktree", "repair"], cwd=self.repo_root)
        publish_event(
            "worktree.repair",
            {
                "root": str(self.settings.root),
                "status": "ok",
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers

    def _enforce_concurrency_limit(self) -> None:
        active = sum(1 for record in self.managed_records() if record.info.path.exists())
        if active >= self.settings.max_concurrency:
            raise WorktreeLimitError(
                f"Maximum active worktrees reached ({self.settings.max_concurrency})."
            )

    def _short_sha(self, ref: str) -> str:
        result = git_run(["rev-parse", "--short", ref], cwd=self.repo_root)
        value = (result.stdout or b"").decode("utf-8", errors="replace").strip()
        if not value:
            raise WorktreeError(f"Unable to resolve short SHA for {ref}")
        return value

    def _ensure_branch_available(self, branch: str) -> None:
        if branch in PROTECTED_BRANCHES:
            raise WorktreeForbiddenError(f"Branch {branch} is protected.")
        for prefix in PROTECTED_PREFIXES:
            if branch.startswith(prefix):
                raise WorktreeForbiddenError(f"Branches prefixed with {prefix} are protected.")

        # Check if branch already exists locally
        result = git_run(
            ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            cwd=self.repo_root,
            check=False,
        )
        if result.returncode == 0:
            raise WorktreeConflictError(f"Branch already exists: {branch}")

        # Ensure no existing worktree uses the same branch
        for record in self.list_records():
            if record.info.branch_short == branch:
                raise WorktreeConflictError(
                    f"Worktree already exists for branch {branch}: {record.info.path}"
                )

    def _ensure_clean(self, path: Path) -> None:
        status = git_run(["status", "--porcelain"], cwd=path)
        output = (status.stdout or b"").decode("utf-8", errors="replace").strip()
        if not output:
            return
        entries = [line for line in output.splitlines() if line.strip()]
        filtered = [line for line in entries if not _is_metadata_entry(line)]
        if filtered:
            raise WorktreeDirtyError(
                f"Worktree {path} has uncommitted changes: {'; '.join(filtered)}"
            )

    def _record_for_path(
        self,
        path: Path,
        *,
        records: list[WorktreeRecord] | None = None,
    ) -> WorktreeRecord:
        resolved = path.resolve()
        source = records or self.list_records()
        for record in source:
            if record.info.path.resolve() == resolved:
                return record
        raise WorktreeNotFoundError(f"Worktree not registered at {resolved}")

    def _resolve_run_id(self, run_id: str) -> WorktreeRecord | None:
        target = sanitize_segment(run_id)
        for record in self.managed_records():
            if record.metadata and record.metadata.run_id == run_id:
                return record
            if record.info.run_id == run_id:
                return record
            if record.info.path.name == run_id:
                return record
            if record.info.path.name.startswith(f"wt-{target}-"):
                return record
        return None

    def _resolve_or_raise(self, run_id: str) -> WorktreeRecord:
        record = self._resolve_run_id(run_id)
        if record is None:
            raise WorktreeNotFoundError(f"No worktree found for run_id={run_id}")
        return record

    def _lock_path(
        self,
        path: Path,
        *,
        reason: str | None = None,
        record: WorktreeRecord | None = None,
        locked: bool = True,
    ) -> None:
        args: list[str] = ["worktree", "lock"]
        if reason:
            args.extend(["--reason", reason])
        args.append(str(path))
        attrs: dict[str, object] = {
            "worktree.path": str(path),
            "worktree.reason": reason or "",
            "worktree.locked": locked,
        }
        if record is not None:
            attrs["worktree.id"] = record.info.path.name
            attrs["worktree.branch"] = record.info.branch_short or "<detached>"
            if record.metadata:
                attrs["worktree.run_id"] = record.metadata.run_id
                attrs["worktree.task"] = record.metadata.task
            else:
                if record.info.run_id:
                    attrs["worktree.run_id"] = record.info.run_id
                if record.info.task_slug:
                    attrs["worktree.task"] = record.info.task_slug
        with trace_span("git.worktree.lock", attrs):
            git_run(args, cwd=self.repo_root)

    def _refresh_active_metric(
        self,
        *,
        records: list[WorktreeRecord] | None = None,
    ) -> None:
        try:
            managed = (
                self.managed_records()
                if records is None
                else self._filter_managed(records)
            )
        except GitCommandError:
            return
        active = sum(1 for record in managed if record.info.path.exists())
        _set_active_count(active)
