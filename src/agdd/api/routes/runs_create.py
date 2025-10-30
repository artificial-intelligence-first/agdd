"""Routes for creating and managing agent runs.

This module provides the POST /runs endpoint for initiating agent executions
with idempotency support.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException, status

from ..config import Settings, get_settings
from ..models import CreateRunRequest, CreateRunResponse
from ..rate_limit import rate_limit_dependency
from ..security import require_api_key, require_scope

# Conditional import to avoid dependency on agent_runner if not available
try:
    from agdd.runners.agent_runner import invoke_mag
except ImportError:
    # For testing or when agent_runner is not available
    def invoke_mag(slug: str, payload: dict[str, Any], base_dir: Path | None, context: dict[str, Any] | None) -> dict[str, Any]:
        """Mock invoke_mag function for testing."""
        if context:
            context["run_id"] = f"mag-test-{int(time.time())}"
        return {"message": "Test execution", "slug": slug}


router = APIRouter(tags=["runs"])


def snapshot_runs(base: Path) -> set[str]:
    """Capture existing run directories before execution.

    Args:
        base: Base directory for runs

    Returns:
        Set of existing run directory names
    """
    if not base.exists():
        return set()
    return {d.name for d in base.iterdir() if d.is_dir()}


def find_new_run_id(
    base: Path,
    before: set[str],
    slug: str,
    started_at: float,
) -> str | None:
    """Find newly created run directory after execution.

    Args:
        base: Base directory for runs
        before: Set of run directories that existed before execution
        slug: Agent slug
        started_at: Timestamp when execution started

    Returns:
        Run ID of new directory, or None if not found
    """
    if not base.exists():
        return None

    after = {d.name for d in base.iterdir() if d.is_dir()}
    new_runs = after - before

    # Filter by timestamp and slug prefix if possible
    candidates = []
    for run_id in new_runs:
        run_path = base / run_id
        try:
            if run_path.stat().st_mtime >= started_at:
                candidates.append(run_id)
        except OSError:
            continue

    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1:
        # Return most recently created
        # Build list of (run_id, mtime) tuples, handling race conditions
        candidates_with_mtime = []
        for run_id in candidates:
            try:
                mtime = (base / run_id).stat().st_mtime
                candidates_with_mtime.append((run_id, mtime))
            except OSError:
                # Directory was deleted between filtering and sorting - skip it
                continue

        if not candidates_with_mtime:
            return None

        # Sort by mtime and return most recent
        candidates_with_mtime.sort(key=lambda x: x[1], reverse=True)
        return candidates_with_mtime[0][0]

    return None


@router.post(
    "/runs",
    response_model=CreateRunResponse,
    dependencies=[Depends(rate_limit_dependency)],
    summary="Create a new agent run",
    description="Execute an agent with the specified payload. Supports idempotency via Idempotency-Key header.",
)
async def create_run(
    req: CreateRunRequest,
    _: str = Depends(require_scope(["agents:run"])),
    settings: Settings = Depends(get_settings),
) -> CreateRunResponse:
    """
    Execute an agent and create a new run.

    This endpoint initiates an agent execution with the provided payload.
    It supports idempotent requests via the Idempotency-Key header or
    idempotency_key field in the request body.

    **Authorization**: Requires "agents:run" scope.

    Args:
        req: Request containing agent slug, payload, and optional idempotency key
        settings: API settings

    Returns:
        Response with run_id and status

    Raises:
        HTTPException:
            - 401: Unauthorized (invalid or missing API key)
            - 403: Forbidden (missing "agents:run" scope)
            - 404: Agent not found
            - 400: Invalid payload or execution failed
            - 409: Idempotency key conflict (handled by middleware)
            - 500: Internal server error
    """
    base = Path(settings.RUNS_BASE_DIR)
    before = snapshot_runs(base)
    started_at = time.time()

    # Create context to receive run_id from invoke_mag
    context: dict[str, Any] = {}

    # Execute agent in thread pool (invoke_mag is blocking)
    # Pass base_dir and context to ensure run_id is returned
    try:
        output: dict[str, Any] = await to_thread.run_sync(
            invoke_mag, req.agent, req.payload, base, context
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "agent_not_found", "message": str(e)},
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_payload", "message": str(e)},
        ) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "execution_failed", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "internal_error", "message": "Unexpected error during execution"},
        ) from e

    # Extract run_id from context (primary method)
    run_id: str | None = context.get("run_id")

    # Fallback: Try to extract run_id from output
    if run_id is None and isinstance(output, dict):
        possible_run_id = output.get("run_id")
        if isinstance(possible_run_id, str):
            run_id = possible_run_id

    # Secondary fallback: Find run_id from filesystem
    if run_id is None:
        run_id = find_new_run_id(base, before, req.agent, started_at)

    # If still no run_id, generate a fallback
    if run_id is None:
        import uuid
        run_id = f"mag-{uuid.uuid4().hex[:8]}"

    # Determine status based on execution result
    # For now, we assume successful completion if no exception was raised
    run_status = "completed"

    return CreateRunResponse(
        run_id=run_id,
        status=run_status,
    )
