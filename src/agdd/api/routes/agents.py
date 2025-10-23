"""Agent execution API endpoints."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml
from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException, status

from agdd.registry import get_registry
from agdd.runners.agent_runner import invoke_mag

from ..config import Settings, get_settings
from ..models import AgentInfo, AgentRunRequest, AgentRunResponse
from ..rate_limit import rate_limit_dependency
from ..run_tracker import find_new_run_id, snapshot_runs
from ..security import require_api_key

router = APIRouter(tags=["agents"])


@router.get(
    "/agents", response_model=list[AgentInfo], dependencies=[Depends(rate_limit_dependency)]
)
async def list_agents(
    _: None = Depends(require_api_key),
    settings: Settings = Depends(get_settings),
) -> list[AgentInfo]:
    """
    List all registered agents by scanning catalog/agents/main/ and catalog/agents/sub/.

    Uses Registry's base_path to resolve agent directories relative to the package,
    ensuring the listing works regardless of CWD.

    Returns:
        List of agent metadata from agent.yaml files
    """
    items: list[AgentInfo] = []

    # Use Registry's base_path (same as Registry uses) to ensure consistency
    registry = get_registry()
    base_path = registry.base_path

    # Scan both main and sub agent directories
    for agent_type in ["main", "sub"]:
        agents_dir = base_path / "agents" / agent_type
        if not agents_dir.exists():
            continue

        for agent_dir in agents_dir.iterdir():
            if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
                continue

            agent_yaml_path = agent_dir / "agent.yaml"
            if not agent_yaml_path.exists():
                continue

            try:
                agent_data = yaml.safe_load(agent_yaml_path.read_text(encoding="utf-8")) or {}
                items.append(
                    AgentInfo(
                        slug=agent_data.get("slug", agent_dir.name),
                        title=agent_data.get("name"),
                        description=agent_data.get("description"),
                    )
                )
            except Exception:
                # Skip agents with invalid YAML
                continue

    return items


@router.post(
    "/agents/{slug}/run",
    response_model=AgentRunResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def run_agent(
    slug: str,
    req: AgentRunRequest,
    _: None = Depends(require_api_key),
    settings: Settings = Depends(get_settings),
) -> AgentRunResponse:
    """
    Execute a MAG agent with given payload.

    Args:
        slug: Agent slug identifier
        req: Request containing payload and optional metadata

    Returns:
        Agent execution response with output and run_id

    Raises:
        HTTPException: 404 if agent not found, 400 for execution errors, 500 for internal errors
    """
    base = Path(settings.RUNS_BASE_DIR)
    before = snapshot_runs(base)
    started_at = time.time()

    # Execute agent in thread pool (invoke_mag is blocking)
    # Pass base_dir to ensure consistency between execution and tracking
    try:
        output: dict[str, Any] = await to_thread.run_sync(invoke_mag, slug, req.payload, base)
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

    # Try to extract run_id from output (future compatibility)
    run_id: str | None = None
    if isinstance(output, dict):
        possible_run_id = output.get("run_id")
        if isinstance(possible_run_id, str):
            run_id = possible_run_id

    # Fallback: Find run_id from filesystem
    if run_id is None:
        run_id = find_new_run_id(base, before, slug, started_at)

    # Build artifacts URLs
    artifacts = None
    if run_id:
        artifacts = {
            "summary": f"{settings.API_PREFIX}/runs/{run_id}",
            "logs": f"{settings.API_PREFIX}/runs/{run_id}/logs",
        }

    return AgentRunResponse(
        run_id=run_id,
        slug=slug,
        output=output,
        artifacts=artifacts,
    )
