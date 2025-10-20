from __future__ import annotations

from pathlib import Path

from tools.lint_registry import collect_registry_errors


def _write_agent(path: Path, agent_id: str, *, skill: str = "echo") -> None:
    path.write_text(
        f"id: {agent_id}\nname: {agent_id}\nversion: 0.0.1\nskills:\n  - {skill}\n",
        encoding="utf-8",
    )


def test_collect_registry_errors_success(tmp_path: Path) -> None:
    agents_dir = tmp_path / "registry" / "agents"
    agents_dir.mkdir(parents=True)
    _write_agent(agents_dir / "a.yaml", "test-agent")

    errors = collect_registry_errors(tmp_path)
    assert errors == []


def test_collect_registry_errors_reports_duplicates(tmp_path: Path) -> None:
    agents_dir = tmp_path / "registry" / "agents"
    agents_dir.mkdir(parents=True)
    _write_agent(agents_dir / "a.yaml", "dup-agent")
    _write_agent(agents_dir / "b.yaml", "dup-agent")

    errors = collect_registry_errors(tmp_path)
    assert any("duplicate agent id" in issue for issue in errors)


def test_collect_registry_errors_reports_missing_skill(tmp_path: Path) -> None:
    agents_dir = tmp_path / "registry" / "agents"
    agents_dir.mkdir(parents=True)
    _write_agent(agents_dir / "a.yaml", "missing-skill", skill="unknown-skill")

    errors = collect_registry_errors(tmp_path)
    assert any("unknown skill" in issue for issue in errors)
