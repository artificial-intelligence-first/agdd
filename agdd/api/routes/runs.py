"""Run observability API endpoints."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ..config import Settings, get_settings
from ..models import RunSummary
from ..run_tracker import open_logs_file, read_metrics, read_summary
from ..security import require_api_key

router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}", response_model=RunSummary)
async def get_run(
    run_id: str,
    _: None = Depends(require_api_key),
    settings: Settings = Depends(get_settings),
) -> RunSummary:
    """
    Get summary and metrics for a completed run.

    Args:
        run_id: Run identifier

    Returns:
        Run summary with metadata, metrics, and log availability

    Raises:
        HTTPException: 404 if run not found
    """
    base = Path(settings.RUNS_BASE_DIR)
    summary = read_summary(base, run_id)
    metrics = read_metrics(base, run_id)
    logs_exist = (base / run_id / "logs.jsonl").exists()

    if not (summary or metrics or logs_exist):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": f"Run not found: {run_id}"},
        )

    return RunSummary(
        run_id=run_id,
        slug=summary.get("slug") if summary else None,
        summary=summary,
        metrics=metrics,
        has_logs=logs_exist,
    )


@router.get("/runs/{run_id}/logs")
async def get_logs(
    run_id: str,
    tail: int | None = Query(default=None, ge=1, description="Return last N lines only"),
    follow: bool = Query(default=False, description="Stream logs in real-time (SSE)"),
    _: None = Depends(require_api_key),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """
    Get logs for a run.

    Args:
        run_id: Run identifier
        tail: Optional number of lines to return from end of file
        follow: If True, stream logs in real-time using Server-Sent Events

    Returns:
        Streaming response with logs (text/event-stream if follow=True, application/x-ndjson otherwise)

    Raises:
        HTTPException: 404 if logs not found
    """
    base = Path(settings.RUNS_BASE_DIR)

    try:
        log_path = open_logs_file(base, run_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": f"Logs not found for run: {run_id}"},
        )

    if follow:
        # Server-Sent Events for real-time streaming
        async def sse_stream() -> AsyncIterator[bytes]:
            async with aiofiles.open(log_path, "r", encoding="utf-8") as f:
                # Optionally send last N lines first
                if tail:
                    content = await f.read()
                    lines = content.splitlines()[-tail:]
                    for line in lines:
                        yield f"data: {line}\n\n".encode("utf-8")
                    # Seek to end for new lines
                    await f.seek(0, 2)
                else:
                    # Start from current end
                    await f.seek(0, 2)

                # Follow new lines
                while True:
                    line = await f.readline()
                    if line:
                        yield f"data: {line.rstrip()}\n\n".encode("utf-8")
                    else:
                        await asyncio.sleep(0.5)

        return StreamingResponse(sse_stream(), media_type="text/event-stream")
    else:
        # NDJSON response (all or tail)
        async def ndjson_stream() -> AsyncIterator[bytes]:
            async with aiofiles.open(log_path, "r", encoding="utf-8") as f:
                if tail:
                    content = await f.read()
                    lines = content.splitlines()[-tail:]
                    for line in lines:
                        yield (line + "\n").encode("utf-8")
                else:
                    # Stream entire file
                    while True:
                        chunk = await f.read(65536)  # 64KB chunks
                        if not chunk:
                            break
                        yield chunk.encode("utf-8") if isinstance(chunk, str) else chunk

        return StreamingResponse(ndjson_stream(), media_type="application/x-ndjson")
