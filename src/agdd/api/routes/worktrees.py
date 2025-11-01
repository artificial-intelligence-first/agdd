"""Git worktree management API endpoints."""

from __future__ import annotations

import json
from typing import AsyncIterator

from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse

from agdd.worktree import (
    GitCommandError,
    WorktreeConflictError,
    WorktreeDirtyError,
    WorktreeError,
    WorktreeForbiddenError,
    WorktreeLimitError,
    WorktreeManager,
    WorktreeNotFoundError,
    WorktreeRecord,
    get_event_bus,
)

from ..models import (
    WorktreeCreateRequest,
    WorktreeLockRequest,
    WorktreeMaintenanceRequest,
    WorktreeResponse,
)
from ..rate_limit import rate_limit_dependency
from ..security import require_scope

router = APIRouter(tags=["worktrees"])


def _record_to_response(record: WorktreeRecord) -> WorktreeResponse:
    meta = record.metadata
    run_id = meta.run_id if meta else record.info.run_id
    task = meta.task if meta else record.info.task_slug
    base = meta.base if meta else None
    short_sha = meta.short_sha if meta else None
    created_at = meta.created_at if meta else None
    detached = record.info.is_detached or (bool(meta.detach) if meta else False)
    no_checkout = bool(meta.no_checkout) if meta else False

    return WorktreeResponse(
        id=record.info.path.name,
        path=str(record.info.path),
        run_id=run_id,
        task=task,
        branch=record.info.branch_short,
        head=record.info.head,
        base=base,
        short_sha=short_sha,
        locked=record.info.locked,
        lock_reason=record.info.lock_reason,
        detached=detached,
        no_checkout=no_checkout,
        prunable=record.info.prunable,
        prunable_reason=record.info.prunable_reason,
        created_at=created_at,
    )


def _worktree_error(exc: WorktreeError) -> HTTPException:
    if isinstance(exc, WorktreeNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
        code = "worktree_not_found"
    elif isinstance(exc, WorktreeConflictError):
        status_code = status.HTTP_409_CONFLICT
        code = "worktree_conflict"
    elif isinstance(exc, WorktreeDirtyError):
        status_code = status.HTTP_409_CONFLICT
        code = "worktree_dirty"
    elif isinstance(exc, WorktreeLimitError):
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
        code = "worktree_limit"
    elif isinstance(exc, WorktreeForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
        code = "worktree_forbidden"
    elif isinstance(exc, GitCommandError):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        code = "worktree_git_error"
    else:
        status_code = status.HTTP_400_BAD_REQUEST
        code = "worktree_error"

    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": str(exc),
        },
    )


@router.get(
    "/worktrees",
    response_model=list[WorktreeResponse],
    dependencies=[Depends(rate_limit_dependency)],
)
async def list_worktrees(
    _: str = Depends(require_scope(["worktrees:read"])),
) -> list[WorktreeResponse]:
    """List managed worktrees."""
    manager = WorktreeManager()
    try:
        records = await to_thread.run_sync(manager.managed_records)
    except WorktreeError as exc:
        raise _worktree_error(exc) from exc
    return [_record_to_response(record) for record in records]


@router.post(
    "/worktrees",
    response_model=WorktreeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_dependency)],
)
async def create_worktree(
    req: WorktreeCreateRequest,
    _: str = Depends(require_scope(["worktrees:write"])),
) -> WorktreeResponse:
    """Create a new managed worktree."""
    manager = WorktreeManager()

    def _create() -> WorktreeRecord:
        return manager.create(
            run_id=req.run_id,
            task=req.task,
            base=req.base,
            detach=req.detach,
            no_checkout=req.no_checkout,
            lock_reason=req.lock_reason,
            auto_lock=req.lock or req.lock_reason is not None,
        )

    try:
        record = await to_thread.run_sync(_create)
    except WorktreeError as exc:
        raise _worktree_error(exc) from exc

    return _record_to_response(record)


@router.delete(
    "/worktrees/{identifier}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit_dependency)],
)
async def remove_worktree(
    identifier: str,
    force: bool = Query(default=False, description="Force removal (CI contexts only)"),
    _: str = Depends(require_scope(["worktrees:write"])),
) -> Response:
    """Remove a managed worktree."""
    manager = WorktreeManager()

    def _remove() -> None:
        manager.remove(identifier, force=force)

    try:
        await to_thread.run_sync(_remove)
    except WorktreeError as exc:
        raise _worktree_error(exc) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/worktrees/{identifier}/lock",
    response_model=WorktreeResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def lock_worktree(
    identifier: str,
    req: WorktreeLockRequest,
    _: str = Depends(require_scope(["worktrees:lock"])),
) -> WorktreeResponse:
    """Lock a worktree to prevent garbage collection."""
    manager = WorktreeManager()

    def _lock() -> WorktreeRecord:
        return manager.lock(identifier, reason=req.reason)

    try:
        record = await to_thread.run_sync(_lock)
    except WorktreeError as exc:
        raise _worktree_error(exc) from exc

    return _record_to_response(record)


@router.post(
    "/worktrees/{identifier}/unlock",
    response_model=WorktreeResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def unlock_worktree(
    identifier: str,
    _: str = Depends(require_scope(["worktrees:unlock"])),
) -> WorktreeResponse:
    """Unlock a managed worktree."""
    manager = WorktreeManager()

    def _unlock() -> WorktreeRecord:
        return manager.unlock(identifier)

    try:
        record = await to_thread.run_sync(_unlock)
    except WorktreeError as exc:
        raise _worktree_error(exc) from exc

    return _record_to_response(record)


@router.post(
    "/worktrees/gc",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit_dependency)],
)
async def prune_worktrees(
    req: WorktreeMaintenanceRequest | None = None,
    _: str = Depends(require_scope(["worktrees:maintain"])),
) -> dict[str, str]:
    """Run git worktree prune."""
    manager = WorktreeManager()
    expire = req.expire if req else None

    def _prune() -> None:
        manager.prune(expire=expire)

    try:
        await to_thread.run_sync(_prune)
    except WorktreeError as exc:
        raise _worktree_error(exc) from exc

    return {"status": "pruned"}


@router.post(
    "/worktrees/repair",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit_dependency)],
)
async def repair_worktrees(
    _: str = Depends(require_scope(["worktrees:maintain"])),
) -> dict[str, str]:
    """Repair git worktree metadata links."""
    manager = WorktreeManager()

    try:
        await to_thread.run_sync(manager.repair)
    except WorktreeError as exc:
        raise _worktree_error(exc) from exc

    return {"status": "repaired"}


@router.get(
    "/worktrees/events",
    dependencies=[Depends(rate_limit_dependency)],
)
async def stream_worktree_events(
    _: str = Depends(require_scope(["worktrees:read"])),
) -> StreamingResponse:
    """Stream worktree lifecycle events via Server-Sent Events."""
    bus = get_event_bus()
    queue = await bus.register()

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            while True:
                event = await queue.get()
                payload = {
                    "timestamp": event.timestamp,
                    "payload": event.payload,
                }
                yield f"event: {event.name}\n".encode("utf-8")
                yield f"data: {json.dumps(payload, ensure_ascii=True)}\n\n".encode("utf-8")
        finally:
            await bus.unregister(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
