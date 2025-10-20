"""Lightweight documentation and changelog policy checks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ensure_files_exist(paths: list[str]) -> list[str]:
    errors: list[str] = []
    for relative in paths:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"Missing required file: {relative}")
    return errors


def validate_changelog(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []

    if "## [Unreleased]" not in text:
        errors.append("CHANGELOG.md must contain an [Unreleased] section")

    release_pattern = re.compile(r"^## \[[^\]]+\] - \d{4}-\d{2}-\d{2}$", re.MULTILINE)
    matches = list(release_pattern.finditer(text))
    if not matches:
        errors.append("CHANGELOG.md must contain at least one dated release entry")
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
    problem_reports.extend(ensure_files_exist(["AGENTS.md", "SSOT.md"]))
    problem_reports.extend(validate_changelog(ROOT / "CHANGELOG.md"))

    if problem_reports:
        for issue in problem_reports:
            print(f"ERROR: {issue}")
        sys.exit(1)

    print("Documentation checks passed.")
