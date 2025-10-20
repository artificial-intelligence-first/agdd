from __future__ import annotations

import functools
import json
import pathlib
from importlib import resources
from typing import Any, Iterable, Iterator, Optional

import typer
import yaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field

from agdd.runners.flowrunner import FlowRunner
from agdd.skills import available_skills, get_skill
from agdd.governance.gate import evaluate as evaluate_flow_summary
from observability.summarize_runs import summarize as summarize_runs


app = typer.Typer(no_args_is_help=True)
flow_app = typer.Typer(help="Flow Runner integration commands")

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY_DIR = ROOT / "registry" / "agents"

CONTRACTS_PACKAGE = "agdd.assets.contracts"
POLICIES_PACKAGE = "agdd.assets.policies"


class AgentDescriptor(BaseModel):
    """Structured view of an agent descriptor."""

    id: str
    name: str
    version: str
    skills: list[str] = Field(default_factory=list, min_length=1)
    metadata: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


def _iter_agent_files() -> Iterator[pathlib.Path]:
    yield from sorted(REGISTRY_DIR.glob("*.y*ml"))


@functools.lru_cache()
def _load_schema() -> dict[str, Any]:
    resource = resources.files(CONTRACTS_PACKAGE).joinpath("agent.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


@functools.lru_cache()
def _schema_validator() -> Draft202012Validator:
    schema = _load_schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _load_agent(path: pathlib.Path) -> AgentDescriptor:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    _schema_validator().validate(data)
    return AgentDescriptor.model_validate(data)


def _resolve_agent(agent_id: str) -> pathlib.Path | None:
    for path in _iter_agent_files():
        if path.stem == agent_id:
            return path
    return None


@app.command()
def validate() -> None:
    """Validate all agent descriptors against the contract schema."""
    count = 0
    for path in _iter_agent_files():
        _load_agent(path)
        count += 1
    typer.echo(f"Validated {count} agent(s). OK.")


def _format_known_skills(skills: Iterable[str]) -> str:
    return ", ".join(sorted(skills)) or "<none>"


@app.command()
def run(agent_id: str, text: str = "hello") -> None:
    """Execute the first registered skill for the requested agent."""
    agent_path = _resolve_agent(agent_id)
    if agent_path is None:
        raise typer.BadParameter(f"Agent '{agent_id}' not found in registry '{REGISTRY_DIR}'.")

    descriptor = _load_agent(agent_path)
    skill_name = descriptor.skills[0]

    try:
        skill = get_skill(skill_name)
    except KeyError as exc:
        known = _format_known_skills(available_skills())
        raise typer.BadParameter(
            f"Skill '{skill_name}' is not available. Known skills: {known}"
        ) from exc

    typer.echo(skill(text))


@flow_app.command("available")
def flow_available() -> None:
    """Check if Flow Runner CLI is installed."""
    runner = FlowRunner()
    typer.echo("yes" if runner.is_available() else "no")


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


app.add_typer(flow_app, name="flow")


if __name__ == "__main__":
    app()
