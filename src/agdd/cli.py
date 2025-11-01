from __future__ import annotations

import asyncio
import json
import pathlib
from typing import TYPE_CHECKING, Any, Optional

import typer

from agdd.worktree import (
    WorktreeError,
    WorktreeManager,
    force_removal_allowed,
)

app = typer.Typer(no_args_is_help=True)
flow_app = typer.Typer(help="Flow Runner integration commands")
agent_app = typer.Typer(help="Agent orchestration commands")
data_app = typer.Typer(help="Data management commands")
mcp_app = typer.Typer(help="Model Context Protocol server commands")
wt_app = typer.Typer(help="Git worktree orchestration commands")


def _handle_worktree_error(exc: WorktreeError) -> None:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(1)


@wt_app.command("new")
def worktree_new(
    run_id: str = typer.Argument(..., help="Unique run identifier"),
    task: str = typer.Option(..., "--task", help="Task slug for the worktree"),
    base: str = typer.Option(..., "--base", help="Base branch or commit-ish"),
    detach: bool = typer.Option(False, "--detach", help="Create a detached HEAD worktree"),
    no_checkout: bool = typer.Option(
        False, "--no-checkout", help="Create worktree without populating working tree"
    ),
    lock: bool = typer.Option(False, "--lock", help="Lock the worktree immediately after creation"),
    lock_reason: Optional[str] = typer.Option(
        None, "--lock-reason", help="Optional reason when locking the worktree"
    ),
) -> None:
    """Create a new managed worktree."""
    manager = WorktreeManager()
    try:
        record = manager.create(
            run_id=run_id,
            task=task,
            base=base,
            detach=detach,
            no_checkout=no_checkout,
            lock_reason=lock_reason,
            auto_lock=lock or lock_reason is not None,
        )
    except WorktreeError as exc:
        _handle_worktree_error(exc)
        return

    branch_display = record.info.branch_short or "<detached>"
    typer.echo(f"Worktree created at {record.info.path}")
    typer.echo(f"  branch: {branch_display}")
    typer.echo(f"  run: {record.metadata.run_id if record.metadata else run_id}")
    typer.echo(f"  task: {record.metadata.task if record.metadata else task}")


@wt_app.command("ls")
def worktree_list(
    json_output: bool = typer.Option(False, "--json", help="Output machine readable JSON"),
) -> None:
    """List managed worktrees."""
    manager = WorktreeManager()
    try:
        records = manager.managed_records()
    except WorktreeError as exc:
        _handle_worktree_error(exc)
        return

    if json_output:
        payload = [record.to_dict() for record in records]
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=True))
        return

    if not records:
        typer.echo("No managed worktrees.")
        return

    header = f"{'RUN':<16} {'TASK':<24} {'BRANCH':<28} {'LOCKED':<6} PATH"
    typer.echo(header)
    for record in records:
        run_value = "-"
        task_value = "-"
        if record.metadata:
            run_value = record.metadata.run_id
            task_value = record.metadata.task
        else:
            run_value = record.info.run_id or "-"
            task_value = record.info.task_slug or "-"
        branch_value = record.info.branch_short or "<detached>"
        locked_value = "yes" if record.info.locked else "no"
        typer.echo(
            f"{run_value:<16.16} {task_value:<24.24} {branch_value:<28.28} {locked_value:<6} {record.info.path}"
        )


@wt_app.command("rm")
def worktree_remove(
    run_id: str = typer.Argument(..., help="Run identifier mapped to the worktree"),
    force: bool = typer.Option(False, "--force", help="Force removal (CI maintenance only)"),
) -> None:
    """Remove a managed worktree."""
    manager = WorktreeManager()
    if force and not force_removal_allowed():
        typer.echo(
            "Error: --force is restricted. Set AGDD_WT_ALLOW_FORCE=1 in CI maintenance context.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        manager.remove(run_id, force=force)
    except WorktreeError as exc:
        _handle_worktree_error(exc)
        return

    typer.echo(f"Worktree for run {run_id} removed.")


@wt_app.command("gc")
def worktree_gc(
    expire: Optional[str] = typer.Option(
        None,
        "--expire",
        help="Expire horizon for prune (defaults to AGDD_WT_TTL).",
    ),
) -> None:
    """Prune stale worktrees."""
    manager = WorktreeManager()
    try:
        manager.prune(expire=expire)
    except WorktreeError as exc:
        _handle_worktree_error(exc)
        return
    typer.echo("Worktree prune completed.")


@wt_app.command("lock")
def worktree_lock(
    run_id: str = typer.Argument(..., help="Run identifier mapped to the worktree"),
    reason: Optional[str] = typer.Option(None, "--reason", help="Optional lock reason"),
) -> None:
    """Lock a worktree to prevent removal or pruning."""
    manager = WorktreeManager()
    try:
        record = manager.lock(run_id, reason=reason)
    except WorktreeError as exc:
        _handle_worktree_error(exc)
        return
    typer.echo(f"Locked worktree at {record.info.path}")


@wt_app.command("unlock")
def worktree_unlock(
    run_id: str = typer.Argument(..., help="Run identifier mapped to the worktree"),
) -> None:
    """Unlock a managed worktree."""
    manager = WorktreeManager()
    try:
        record = manager.unlock(run_id)
    except WorktreeError as exc:
        _handle_worktree_error(exc)
        return
    typer.echo(f"Unlocked worktree at {record.info.path}")


@wt_app.command("repair")
def worktree_repair() -> None:
    """Repair worktree admin files when paths were moved manually."""
    manager = WorktreeManager()
    try:
        manager.repair()
    except WorktreeError as exc:
        _handle_worktree_error(exc)
        return
    typer.echo("Worktree repair completed.")


@flow_app.command("available")
def flow_available() -> None:
    """Check if Flow Runner CLI is installed."""
    # Lazy import to reduce startup time
    from agdd.runners.flowrunner import FlowRunner

    runner = FlowRunner()
    if not runner.is_available():
        typer.echo("no")
        return

    info = runner.info()
    capabilities = ", ".join(sorted(info.capabilities)) or "<none>"
    typer.echo(f"yes ({info.name} {info.version}; capabilities: {capabilities})")


@flow_app.command("validate")
def flow_validate(
    path: pathlib.Path,
    schema: Optional[pathlib.Path] = typer.Option(
        None,
        "--schema",
        help="Optional schema file to use during validation.",
    ),
) -> None:
    """Validate a flow definition using Flow Runner."""
    # Lazy import to reduce startup time
    from agdd.runners.flowrunner import FlowRunner

    runner = FlowRunner()
    result = runner.validate(path, schema=schema)
    if not result.ok:
        if result.stderr:
            typer.echo(result.stderr)
        raise typer.Exit(1)
    typer.echo(result.stdout or "OK")


@flow_app.command("run")
def flow_run(
    path: pathlib.Path,
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview execution without side effects."
    ),
    only: Optional[str] = typer.Option(None, "--only", help="Run only the specified flow step."),
    continue_from: Optional[str] = typer.Option(
        None, "--continue-from", help="Resume execution from the given step."
    ),
) -> None:
    """Execute a flow definition via Flow Runner."""
    # Lazy import to reduce startup time
    from agdd.runners.flowrunner import FlowRunner

    runner = FlowRunner()
    result = runner.run(path, dry_run=dry_run, only=only, continue_from=continue_from)
    if not result.ok:
        if result.stderr:
            typer.echo(result.stderr)
        raise typer.Exit(1)
    typer.echo(result.stdout)


@flow_app.command("summarize")
def flow_summarize(
    base: pathlib.Path = typer.Option(
        pathlib.Path(".runs"),
        "--base",
        help="Directory that contains Flow Runner run artifacts.",
    ),
    output: pathlib.Path | None = typer.Option(
        None,
        "--output",
        help="Optional path to write the JSON report.",
    ),
) -> None:
    """Summarize Flow Runner run outputs from the specified directory."""
    # Lazy import to reduce startup time
    from agdd.observability.summarize_runs import summarize as summarize_runs

    report = summarize_runs(base)
    payload = json.dumps(report, ensure_ascii=False)
    if output is not None:
        output.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)


@flow_app.command("gate")
def flow_gate(
    summary: pathlib.Path = typer.Argument(..., exists=True, dir_okay=False),
    policy: pathlib.Path | None = typer.Option(
        None,
        "--policy",
        help="Policy file describing governance thresholds (defaults to bundled policy).",
    ),
) -> None:
    """Evaluate governance thresholds against a flow summary."""
    # Lazy import to reduce startup time
    from agdd.governance.gate import evaluate as evaluate_flow_summary

    issues = evaluate_flow_summary(summary, policy)
    if issues:
        typer.echo("GOVERNANCE GATE FAILED")
        for issue in issues:
            typer.echo(f"- {issue}")
        raise typer.Exit(2)

    typer.echo("GOVERNANCE GATE PASSED")


@agent_app.command("run")
def agent_run(
    slug: str = typer.Argument(..., help="Agent slug (e.g., 'offer-orchestrator-mag')"),
    json_input: Optional[pathlib.Path] = typer.Option(
        None,
        "--json",
        help="JSON file containing input payload (reads from stdin if '-' or omitted).",
    ),
    deterministic: bool = typer.Option(
        False,
        "--deterministic",
        help="Enable deterministic mode for reproducible execution",
    ),
    replay: Optional[str] = typer.Option(
        None,
        "--replay",
        help="Path to replay snapshot JSON file for reproducing a previous run",
    ),
) -> None:
    """Execute a MAG agent with JSON input."""
    import sys

    # Lazy import to reduce startup time
    from agdd.runners.agent_runner import invoke_mag
    from agdd.runner_determinism import (
        set_deterministic_mode,
        snapshot_environment,
        create_replay_context,
    )

    # Read input
    if json_input is None or str(json_input) == "-":
        data = json.load(sys.stdin)
    else:
        data = json.loads(json_input.read_text(encoding="utf-8"))

    # Prepare execution context
    context: dict[str, Any] = {}

    # Handle replay mode
    if replay is not None:
        replay_path = pathlib.Path(replay)
        if not replay_path.exists():
            typer.echo(f"Error: Replay file not found: {replay}", err=True)
            raise typer.Exit(1)
        try:
            replay_data = json.loads(replay_path.read_text(encoding="utf-8"))

            # Extract environment_snapshot if present (from summary.json)
            # Otherwise use the data directly (raw snapshot format)
            if "environment_snapshot" in replay_data:
                replay_snapshot = replay_data["environment_snapshot"]
            else:
                replay_snapshot = replay_data

            context = create_replay_context(replay_snapshot, context)
        except Exception as e:
            typer.echo(f"Error loading replay snapshot: {e}", err=True)
            raise typer.Exit(1)

    # Handle deterministic mode
    if deterministic:
        set_deterministic_mode(True)
        context["deterministic"] = True
        context["environment_snapshot"] = snapshot_environment()

    try:
        # Invoke MAG with context
        output = invoke_mag(slug, data, context=context)
        # Output result as JSON
        typer.echo(json.dumps(output, ensure_ascii=False, indent=2))
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Execution failed: {e}", err=True)
        raise typer.Exit(2)


@data_app.command("init")
def data_init(
    backend: str = typer.Option("sqlite", "--backend", help="Storage backend: sqlite, postgres"),
    db_path: str = typer.Option(
        ".agdd/storage.db", "--db-path", help="Database path (sqlite only)"
    ),
    enable_fts: bool = typer.Option(True, "--fts/--no-fts", help="Enable FTS5 full-text search"),
) -> None:
    """Initialize storage backend"""
    from agdd.api.config import Settings
    from agdd.storage import create_storage_backend

    settings = Settings(
        STORAGE_BACKEND=backend,
        STORAGE_DB_PATH=db_path,
        STORAGE_ENABLE_FTS=enable_fts,
    )

    async def _init() -> None:
        storage = await create_storage_backend(settings)
        typer.echo(f"Storage initialized: {backend}")
        typer.echo(f"  Capabilities: {storage.capabilities}")
        await storage.close()

    asyncio.run(_init())


@data_app.command("vacuum")
def data_vacuum(
    hot_days: int = typer.Option(7, "--hot-days", help="Keep data newer than this many days"),
    max_disk_mb: Optional[int] = typer.Option(
        None, "--max-disk", help="Target maximum disk usage in MB"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only report what would be deleted"),
) -> None:
    """Clean up old data based on retention policy"""
    from agdd.storage import get_storage_backend

    async def _vacuum() -> None:
        storage = await get_storage_backend()
        try:
            result = await storage.vacuum(
                hot_days=hot_days, max_disk_mb=max_disk_mb, dry_run=dry_run
            )
            typer.echo(json.dumps(result, indent=2))
        finally:
            await storage.close()

    asyncio.run(_vacuum())


@data_app.command("archive")
def data_archive(
    destination: str = typer.Argument(
        ..., help="Archive destination URI (e.g., s3://bucket/prefix)"
    ),
    since_days: int = typer.Option(7, "--since", help="Archive data older than this many days"),
    format: str = typer.Option("parquet", "--format", help="Archive format: parquet, ndjson"),
) -> None:
    """Archive old data to external storage (S3, MinIO, etc.)"""
    from agdd.storage import get_storage_backend

    async def _archive() -> None:
        storage = await get_storage_backend()
        try:
            result = await storage.archive(
                destination=destination, since_days=since_days, format=format
            )
            typer.echo(json.dumps(result, indent=2))
        finally:
            await storage.close()

    asyncio.run(_archive())


@data_app.command("query")
def data_query(
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Filter by run ID"),
    agent: Optional[str] = typer.Option(None, "--agent", help="Filter by agent slug"),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
    limit: int = typer.Option(10, "--limit", help="Maximum number of results"),
) -> None:
    """Query runs and events from storage"""
    from agdd.storage import get_storage_backend

    async def _query() -> None:
        storage = await get_storage_backend()
        try:
            if run_id:
                # Get specific run
                run = await storage.get_run(run_id)
                if run:
                    typer.echo(json.dumps(run, indent=2))
                else:
                    typer.echo(f"Run not found: {run_id}", err=True)
                    raise typer.Exit(1)
            else:
                # List runs
                runs = await storage.list_runs(agent_slug=agent, status=status, limit=limit)
                typer.echo(json.dumps(runs, indent=2))
        finally:
            await storage.close()

    asyncio.run(_query())


@data_app.command("search")
def data_search(
    query: str = typer.Argument(..., help="Search query"),
    agent: Optional[str] = typer.Option(None, "--agent", help="Filter by agent slug"),
    limit: int = typer.Option(100, "--limit", help="Maximum number of results"),
) -> None:
    """Full-text search across event messages (requires FTS5)"""
    from agdd.storage import get_storage_backend

    async def _search() -> None:
        storage = await get_storage_backend()
        try:
            if not storage.capabilities.search_text:
                typer.echo("Error: Full-text search not supported by this backend", err=True)
                raise typer.Exit(1)

            results = await storage.search_text(query=query, agent_slug=agent, limit=limit)
            typer.echo(json.dumps(results, indent=2))
        finally:
            await storage.close()

    asyncio.run(_search())


@mcp_app.command("serve")
def mcp_serve(
    agents: bool = typer.Option(True, "--agents/--no-agents", help="Expose agents as MCP tools"),
    skills: bool = typer.Option(False, "--skills/--no-skills", help="Expose skills as MCP tools"),
    agent_filter: Optional[str] = typer.Option(
        None, "--filter-agents", help="Comma-separated list of agent slugs to expose"
    ),
    skill_filter: Optional[str] = typer.Option(
        None, "--filter-skills", help="Comma-separated list of skill IDs to expose"
    ),
) -> None:
    """Start AGDD as an MCP server exposing agents and skills as tools.

    This command starts an MCP server that allows external clients (like Claude Desktop)
    to invoke AGDD agents and skills through the Model Context Protocol.

    Example Claude Desktop configuration (~/.config/Claude/claude_desktop_config.json):

        {
          "mcpServers": {
            "agdd": {
              "command": "agdd",
              "args": ["mcp", "serve"]
            }
          }
        }

    To expose specific agents only:

        agdd mcp serve --filter-agents offer-orchestrator-mag,compensation-advisor-sag
    """
    try:
        from agdd.mcp.server_provider import create_server
    except ImportError as e:
        typer.echo(
            "Error: MCP SDK not installed. Install with: pip install mcp",
            err=True,
        )
        raise typer.Exit(1) from e

    # Parse filters
    agent_list = None
    if agent_filter:
        agent_list = [s.strip() for s in agent_filter.split(",")]

    skill_list = None
    if skill_filter:
        skill_list = [s.strip() for s in skill_filter.split(",")]

    # Create and run server
    try:
        server = create_server(
            expose_agents=agents,
            expose_skills=skills,
            agent_filter=agent_list,
            skill_filter=skill_list,
        )
        server.run(transport="stdio")
    except Exception as e:
        typer.echo(f"MCP server failed: {e}", err=True)
        raise typer.Exit(2)


app.add_typer(flow_app, name="flow")
app.add_typer(agent_app, name="agent")
app.add_typer(data_app, name="data")
app.add_typer(mcp_app, name="mcp")
app.add_typer(wt_app, name="wt")

# Catalog management commands
if TYPE_CHECKING:
    from agdd.cli_catalog import app as catalog_app
else:
    try:
        from agdd.cli_catalog import app as catalog_app

        app.add_typer(catalog_app, name="catalog")
    except ImportError:
        # Catalog CLI not available (missing dependencies like jsonschema)
        pass


if __name__ == "__main__":
    app()
