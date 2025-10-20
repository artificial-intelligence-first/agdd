"""Static checks for agent registry declarations."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

import yaml
from pydantic import ValidationError

from agdd.cli import AgentDescriptor
from agdd.skills import available_skills


def _iter_agent_files(root: Path) -> Iterable[Path]:
    agents_dir = root / "registry" / "agents"
    if not agents_dir.exists():
        return []
    return sorted(agents_dir.glob("*.y*ml"))


def collect_registry_errors(root: Path) -> list[str]:
    """Return a list of lint violations for the agent registry."""
    errors: list[str] = []
    seen_ids: dict[str, Path] = {}
    known_skills = set(available_skills())

    agent_files = list(_iter_agent_files(root))
    if not agent_files:
        errors.append("registry/agents directory has no agent descriptors")
        return errors

    for path in agent_files:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            errors.append(f"{path}: invalid YAML ({exc})")
            continue

        try:
            descriptor = AgentDescriptor.model_validate(data)
        except ValidationError as exc:
            errors.append(f"{path}: validation error ({exc})")
            continue

        existing = seen_ids.get(descriptor.id)
        if existing is not None:
            errors.append(
                f"duplicate agent id '{descriptor.id}' in {path} (previously defined in {existing})"
            )
        else:
            seen_ids[descriptor.id] = path

        for skill in descriptor.skills:
            if skill not in known_skills:
                errors.append(
                    f"agent '{descriptor.id}' references unknown skill '{skill}' in {path}"
                )

    return errors


def main() -> int:
    errors = collect_registry_errors(Path.cwd())
    if errors:
        for issue in errors:
            print(issue, file=sys.stderr)
        return 1

    print("Registry lint passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
