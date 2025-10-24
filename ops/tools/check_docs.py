"""Lightweight documentation and changelog policy checks."""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def ensure_files_exist(paths: list[str]) -> list[str]:
    errors: list[str] = []
    for relative in paths:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"Missing required file: {relative}")
    return errors


def validate_front_matter(path: Path) -> list[str]:
    """Validate YAML front-matter in documentation files."""
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    warnings: list[str] = []

    # Check for front-matter presence
    if not text.startswith("---\n"):
        errors.append(f"{path.relative_to(ROOT)}: Missing YAML front-matter (must start with '---')")
        return errors

    # Extract front-matter
    lines = text.split("\n")
    front_matter_end = -1
    for i in range(1, min(len(lines), 50)):  # Search first 50 lines
        if lines[i].strip() == "---":
            front_matter_end = i
            break

    if front_matter_end == -1:
        errors.append(f"{path.relative_to(ROOT)}: Front-matter not properly closed with '---'")
        return errors

    front_matter = "\n".join(lines[1:front_matter_end])

    # Check required fields
    required_fields = ["title:", "last_synced:", "description:"]
    for field in required_fields:
        if field not in front_matter:
            errors.append(f"{path.relative_to(ROOT)}: Missing required field '{field.rstrip(':')}'")

    # Validate last_synced format (YYYY-MM-DD)
    last_synced_match = re.search(r"last_synced:\s*(\d{4}-\d{2}-\d{2})", front_matter)
    if last_synced_match:
        try:
            sync_date = datetime.strptime(last_synced_match.group(1), "%Y-%m-%d")
            days_old = (datetime.now() - sync_date).days
            if days_old > 90:
                warnings.append(
                    f"{path.relative_to(ROOT)}: last_synced is {days_old} days old "
                    "(consider updating if content changed)"
                )
        except ValueError:
            errors.append(f"{path.relative_to(ROOT)}: Invalid last_synced date format")

    # Check for source_of_truth when appropriate (optional but good practice)
    if "ssot" in path.name.lower() or "agent" in path.name.lower():
        if "source_of_truth:" not in front_matter:
            warnings.append(
                f"{path.relative_to(ROOT)}: Consider adding 'source_of_truth' link to SSOT repository"
            )

    # Print warnings (non-blocking)
    for warning in warnings:
        print(f"WARNING: {warning}")

    return errors


def validate_changelog(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []

    if "## [Unreleased]" not in text:
        errors.append("docs/development/changelog.md must contain an [Unreleased] section")

    release_pattern = re.compile(r"^## \[[^\]]+\] - \d{4}-\d{2}-\d{2}$", re.MULTILINE)
    matches = list(release_pattern.finditer(text))
    if not matches:
        errors.append("docs/development/changelog.md must contain at least one dated release entry")
        return errors

    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        section = text[start:end]
        for heading in ("### Added", "### Changed", "### Fixed"):
            if heading not in section:
                errors.append(
                    f"CHANGELOG release '{match.group(0)}' is missing heading: {heading}"
                )
    return errors


if __name__ == "__main__":
    problem_reports: list[str] = []
    problem_reports.extend(
        ensure_files_exist(
            [
                "docs/guides/agent-development.md",
                "docs/reference/ssot.md",
                "docs/development/roadmap.md",
                "README.md",
                "docs/development/changelog.md",
                "docs/guides/runner-integration.md",
            ]
        )
    )
    problem_reports.extend(validate_changelog(ROOT / "docs" / "development" / "changelog.md"))

    # Validate front-matter in all documentation files
    docs_with_frontmatter = [
        "docs/reference/ssot.md",
        "docs/guides/agent-development.md",
        "docs/guides/api-usage.md",
        "docs/guides/a2a-communication.md",
        "docs/guides/cost-optimization.md",
        "docs/guides/github-integration.md",
        "docs/guides/mcp-integration.md",
        "docs/guides/moderation.md",
        "docs/guides/multi-provider.md",
        "docs/guides/runner-integration.md",
        "docs/guides/semantic-cache.md",
        "docs/development/changelog.md",
        "docs/development/contributing.md",
        "docs/development/roadmap.md",
        "docs/storage.md",
        "docs/policies/security.md",
        "docs/policies/code-of-conduct.md",
    ]

    for doc_path in docs_with_frontmatter:
        full_path = ROOT / doc_path
        if full_path.exists():
            problem_reports.extend(validate_front_matter(full_path))

    if problem_reports:
        for issue in problem_reports:
            print(f"ERROR: {issue}")
        sys.exit(1)

    print("✓ Documentation checks passed.")
