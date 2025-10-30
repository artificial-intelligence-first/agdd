"""Catalog management CLI commands."""

from __future__ import annotations

import json
import pathlib
from typing import Optional

import typer
import yaml

app = typer.Typer(help="Catalog management commands")

# Schema mapping for different catalog file types
SCHEMA_MAP = {
    "agent.yaml": "catalog/_schemas/agent.schema.json",
    "skill.yaml": "catalog/_schemas/skill.schema.json",
    "eval.yaml": "catalog/_schemas/eval.schema.json",
    "flow_governance.yaml": "catalog/_schemas/policy.schema.json",
}

# Routing policies use a separate schema
ROUTING_SCHEMA = "catalog/_schemas/routing.schema.json"


def _find_catalog_files() -> list[tuple[pathlib.Path, str]]:
    """Find all catalog YAML files and their associated schemas.

    Returns:
        List of (file_path, schema_path) tuples
    """
    import pathlib

    repo_root = pathlib.Path.cwd()
    catalog_dir = repo_root / "catalog"

    files_with_schemas: list[tuple[pathlib.Path, str]] = []

    # Find agent files
    for agent_file in catalog_dir.glob("agents/**/*.yaml"):
        if agent_file.name == "agent.yaml":
            files_with_schemas.append((agent_file, SCHEMA_MAP["agent.yaml"]))

    # Find skill files
    for skill_file in catalog_dir.glob("skills/**/*.yaml"):
        if skill_file.name == "skill.yaml":
            files_with_schemas.append((skill_file, SCHEMA_MAP["skill.yaml"]))

    # Find eval files
    for eval_file in catalog_dir.glob("evals/**/*.yaml"):
        if eval_file.name == "eval.yaml":
            files_with_schemas.append((eval_file, SCHEMA_MAP["eval.yaml"]))

    # Find policy files
    for policy_file in catalog_dir.glob("policies/*.yaml"):
        files_with_schemas.append((policy_file, SCHEMA_MAP["flow_governance.yaml"]))

    # Find routing policy files
    for routing_file in catalog_dir.glob("routing/policies/*.yaml"):
        files_with_schemas.append((routing_file, ROUTING_SCHEMA))

    return files_with_schemas


def _validate_yaml_against_schema(
    yaml_path: pathlib.Path, schema_path: pathlib.Path
) -> tuple[bool, Optional[str]]:
    """Validate a YAML file against a JSON schema.

    Args:
        yaml_path: Path to YAML file
        schema_path: Path to JSON schema file

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        import jsonschema
    except ImportError:
        return False, "jsonschema package not installed. Install with: pip install jsonschema"

    try:
        # Load YAML file
        with open(yaml_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)

        # Load schema
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        # Validate
        jsonschema.validate(instance=yaml_data, schema=schema)
        return True, None
    except jsonschema.ValidationError as e:
        return False, f"Validation error: {e.message}\n  Path: {' -> '.join(str(p) for p in e.path)}"
    except yaml.YAMLError as e:
        return False, f"YAML parsing error: {e}"
    except FileNotFoundError as e:
        return False, f"File not found: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


@app.command("validate")
def validate(
    path: Optional[pathlib.Path] = typer.Option(
        None,
        "--path",
        help="Specific file or directory to validate (defaults to all catalog files)",
    ),
    schema: Optional[pathlib.Path] = typer.Option(
        None,
        "--schema",
        help="Specific schema file to use (auto-detected if not provided)",
    ),
) -> None:
    """Validate catalog files against their JSON schemas.

    By default, validates all catalog files (agents, skills, evals, policies, routing).
    Use --path to validate a specific file or directory.
    """
    repo_root = pathlib.Path.cwd()

    # If specific path provided, validate only that
    if path:
        if not path.exists():
            typer.echo(f"Error: Path does not exist: {path}", err=True)
            raise typer.Exit(1)

        # Determine schema
        if schema:
            schema_path = schema
        else:
            # Auto-detect schema based on filename
            filename = path.name
            if filename not in SCHEMA_MAP:
                typer.echo(
                    f"Error: Could not determine schema for {filename}. "
                    f"Use --schema to specify manually.",
                    err=True,
                )
                raise typer.Exit(1)
            schema_path = repo_root / SCHEMA_MAP[filename]

        # Validate single file
        is_valid, error = _validate_yaml_against_schema(path, schema_path)
        if is_valid:
            typer.echo(f"✓ {path.relative_to(repo_root)}")
        else:
            typer.echo(f"✗ {path.relative_to(repo_root)}")
            typer.echo(f"  {error}")
            raise typer.Exit(1)
        return

    # Validate all catalog files
    files_with_schemas = _find_catalog_files()

    if not files_with_schemas:
        typer.echo("No catalog files found to validate.")
        return

    total = len(files_with_schemas)
    valid = 0
    invalid = 0

    for yaml_path, schema_rel_path in files_with_schemas:
        schema_path = repo_root / schema_rel_path
        is_valid, error = _validate_yaml_against_schema(yaml_path, schema_path)

        rel_path = yaml_path.relative_to(repo_root)
        if is_valid:
            typer.echo(f"✓ {rel_path}")
            valid += 1
        else:
            typer.echo(f"✗ {rel_path}")
            typer.echo(f"  {error}")
            invalid += 1

    # Summary
    typer.echo("")
    typer.echo(f"Validated {total} files: {valid} passed, {invalid} failed")

    if invalid > 0:
        raise typer.Exit(1)


@app.command("migrate")
def migrate(
    from_version: str = typer.Option(..., "--from", help="Source schema version (e.g., 'v1')"),
    to_version: str = typer.Option(..., "--to", help="Target schema version (e.g., 'v2')"),
    path: Optional[pathlib.Path] = typer.Option(
        None,
        "--path",
        help="Specific file or directory to migrate (defaults to all catalog files)",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply the migration (default: dry-run mode shows plan only)",
    ),
) -> None:
    """Generate or execute migration plan for catalog schema upgrades.

    By default, this command runs in dry-run mode and only shows what would be changed.
    Use --apply to actually execute the migration.

    Example:
        agdd catalog migrate --from v1 --to v2          # Show migration plan
        agdd catalog migrate --from v1 --to v2 --apply  # Execute migration
    """
    repo_root = pathlib.Path.cwd()

    # Find files to migrate
    if path:
        if not path.exists():
            typer.echo(f"Error: Path does not exist: {path}", err=True)
            raise typer.Exit(1)
        files = [path] if path.is_file() else list(path.glob("**/*.yaml"))
    else:
        files_with_schemas = _find_catalog_files()
        files = [f for f, _ in files_with_schemas]

    if not files:
        typer.echo("No files found to migrate.")
        return

    # Display migration plan
    typer.echo(f"Migration Plan: {from_version} → {to_version}")
    typer.echo("=" * 60)
    typer.echo("")

    migration_count = 0
    for file_path in files:
        rel_path = file_path.relative_to(repo_root)

        # In a real implementation, we would:
        # 1. Load the file
        # 2. Detect its current version
        # 3. Apply transformations based on migration rules
        # 4. Optionally write back if --apply is set

        # For now, we just show what would be migrated
        typer.echo(f"  • {rel_path}")
        migration_count += 1

    typer.echo("")
    typer.echo(f"Total files to migrate: {migration_count}")
    typer.echo("")

    if apply:
        typer.echo("⚠️  Migration execution is not yet implemented.")
        typer.echo("This is a placeholder for future schema migration functionality.")
        typer.echo("")
        typer.echo("Planned migration steps:")
        typer.echo("  1. Backup original files")
        typer.echo("  2. Apply schema transformations")
        typer.echo("  3. Validate against new schema")
        typer.echo("  4. Update version fields")
        raise typer.Exit(1)
    else:
        typer.echo("ℹ️  This is a dry-run. No files were modified.")
        typer.echo("   Use --apply to execute the migration.")


if __name__ == "__main__":
    app()
