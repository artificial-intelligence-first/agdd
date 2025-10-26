from __future__ import annotations

import asyncio
import json
import pathlib
from typing import Optional

import typer

from agdd.governance.gate import evaluate as evaluate_flow_summary
from agdd.runners.agent_runner import invoke_mag
from agdd.runners.flowrunner import FlowRunner
from agdd.observability.summarize_runs import summarize as summarize_runs

app = typer.Typer(no_args_is_help=True)
flow_app = typer.Typer(help="Flow Runner integration commands")
agent_app = typer.Typer(help="Agent orchestration commands")
data_app = typer.Typer(help="Data management commands")
mcp_app = typer.Typer(help="Model Context Protocol server commands")


@flow_app.command("available")
def flow_available() -> None:
    """Check if Flow Runner CLI is installed."""
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
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview execution without side effects."),
    only: Optional[str] = typer.Option(None, "--only", help="Run only the specified flow step."),
    continue_from: Optional[str] = typer.Option(
        None, "--continue-from", help="Resume execution from the given step."
    ),
) -> None:
    """Execute a flow definition via Flow Runner."""
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
) -> None:
    """Execute a MAG agent with JSON input."""
    import sys

    # Read input
    if json_input is None or str(json_input) == "-":
        data = json.load(sys.stdin)
    else:
        data = json.loads(json_input.read_text(encoding="utf-8"))

    try:
        # Invoke MAG
        output = invoke_mag(slug, data)
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
    db_path: str = typer.Option(".agdd/storage.db", "--db-path", help="Database path (sqlite only)"),
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
    destination: str = typer.Argument(..., help="Archive destination URI (e.g., s3://bucket/prefix)"),
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
                typer.echo(
                    "Error: Full-text search not supported by this backend", err=True
                )
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


if __name__ == "__main__":
    app()
