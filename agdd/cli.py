from __future__ import annotations

import json
import pathlib
from typing import Optional

import typer

from agdd.governance.gate import evaluate as evaluate_flow_summary
from agdd.runners.agent_runner import invoke_mag
from agdd.runners.flowrunner import FlowRunner
from observability.summarize_runs import summarize as summarize_runs

app = typer.Typer(no_args_is_help=True)
flow_app = typer.Typer(help="Flow Runner integration commands")
agent_app = typer.Typer(help="Agent orchestration commands")


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


app.add_typer(flow_app, name="flow")
app.add_typer(agent_app, name="agent")


if __name__ == "__main__":
    app()
