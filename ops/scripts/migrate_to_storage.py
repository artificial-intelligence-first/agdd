#!/usr/bin/env python3
"""
Migrate legacy file-based observability data to new storage layer.

This script reads data from .runs/agents/ directory and imports it into
the new storage backend (SQLite by default).

Usage:
    python scripts/migrate_to_storage.py --source .runs/agents --dry-run
    python scripts/migrate_to_storage.py --source .runs/agents
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import typer

app = typer.Typer()


async def migrate_run(
    run_dir: Path,
    storage: Any,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Migrate a single run from file-based to storage.

    Args:
        run_dir: Path to run directory
        storage: Storage backend instance
        dry_run: If True, only report what would be migrated

    Returns:
        Migration report
    """
    run_id = run_dir.name
    report = {
        "run_id": run_id,
        "status": "pending",
        "events_migrated": 0,
        "errors": [],
    }

    try:
        # Read summary.json
        summary_file = run_dir / "summary.json"
        if not summary_file.exists():
            report["status"] = "skipped"
            report["errors"].append("summary.json not found")
            return report

        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        agent_slug = summary.get("slug", "unknown")

        if dry_run:
            report["status"] = "dry_run"
            typer.echo(f"[DRY RUN] Would migrate run: {run_id} (agent: {agent_slug})")
            return report

        # Create run record
        # Infer timestamps from logs
        logs_file = run_dir / "logs.jsonl"
        started_at = datetime.now(timezone.utc)
        ended_at = None
        status = "succeeded"

        if logs_file.exists():
            with open(logs_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if lines:
                    # First event
                    first_event = json.loads(lines[0])
                    started_at = datetime.fromtimestamp(
                        first_event["timestamp"], tz=timezone.utc
                    )

                    # Last event
                    last_event = json.loads(lines[-1])
                    ended_at = datetime.fromtimestamp(
                        last_event["timestamp"], tz=timezone.utc
                    )

                    # Check for errors
                    for line in lines:
                        event = json.loads(line)
                        if event.get("event") == "error":
                            status = "failed"
                            break

        await storage.create_run(
            run_id=run_id,
            agent_slug=agent_slug,
            started_at=started_at,
            status=status,
        )

        # Migrate logs
        if logs_file.exists():
            with open(logs_file, "r", encoding="utf-8") as f:
                for line in f:
                    event = json.loads(line)
                    timestamp = datetime.fromtimestamp(
                        event["timestamp"], tz=timezone.utc
                    )

                    # Determine event type and level
                    event_name = event.get("event", "log")
                    level = "info"
                    if event_name in ("error", "retry"):
                        level = "error"

                    await storage.append_event(
                        run_id=run_id,
                        agent_slug=agent_slug,
                        event_type="log",
                        timestamp=timestamp,
                        level=level,
                        message=f"{event_name}: {event.get('data', {})}",
                        payload=event.get("data", {}),
                    )

                    report["events_migrated"] += 1

        # Update run with metrics
        metrics_file = run_dir / "metrics.json"
        if metrics_file.exists():
            metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
            # Flatten metrics
            flat_metrics = {}
            for key, values in metrics.items():
                if isinstance(values, list) and values:
                    # Take last value
                    flat_metrics[key] = values[-1].get("value")

            await storage.update_run(
                run_id=run_id,
                status=status,
                ended_at=ended_at,
                metrics=flat_metrics,
            )

        report["status"] = "success"

    except Exception as e:
        report["status"] = "error"
        report["errors"].append(str(e))

    return report


@app.command()
def migrate(
    source: Path = typer.Option(
        Path(".runs/agents"),
        "--source",
        help="Source directory containing run artifacts",
    ),
    backend: str = typer.Option(
        "sqlite", "--backend", help="Storage backend: sqlite, postgres"
    ),
    db_path: str = typer.Option(
        ".agdd/storage.db", "--db-path", help="Database path (sqlite only)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Only report what would be migrated"
    ),
) -> None:
    """Migrate legacy file-based observability data to new storage layer"""
    from agdd.api.config import Settings
    from agdd.storage import create_storage_backend

    async def _migrate() -> None:
        # Initialize storage
        settings = Settings(
            STORAGE_BACKEND=backend,
            STORAGE_DB_PATH=db_path,
        )

        storage = await create_storage_backend(settings)

        try:
            # Find all run directories
            if not source.exists():
                typer.echo(f"Error: Source directory not found: {source}", err=True)
                raise typer.Exit(1)

            run_dirs: List[Path] = []
            for item in source.iterdir():
                if item.is_dir():
                    run_dirs.append(item)

            typer.echo(f"Found {len(run_dirs)} runs to migrate")

            # Migrate each run
            reports: List[Dict[str, Any]] = []
            for run_dir in run_dirs:
                report = await migrate_run(run_dir, storage, dry_run=dry_run)
                reports.append(report)

                status_icon = "✓" if report["status"] == "success" else "✗"
                typer.echo(
                    f"{status_icon} {report['run_id']}: {report['status']} "
                    f"({report['events_migrated']} events)"
                )

                if report["errors"]:
                    for error in report["errors"]:
                        typer.echo(f"  Error: {error}", err=True)

            # Summary
            typer.echo("\nMigration Summary:")
            typer.echo(f"  Total runs: {len(reports)}")
            typer.echo(
                f"  Successful: {sum(1 for r in reports if r['status'] == 'success')}"
            )
            typer.echo(
                f"  Failed: {sum(1 for r in reports if r['status'] == 'error')}"
            )
            typer.echo(
                f"  Skipped: {sum(1 for r in reports if r['status'] == 'skipped')}"
            )
            typer.echo(
                f"  Total events: {sum(r['events_migrated'] for r in reports)}"
            )

        finally:
            await storage.close()

    asyncio.run(_migrate())


if __name__ == "__main__":
    app()
