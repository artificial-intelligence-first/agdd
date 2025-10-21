# AG-Driven Development (AGDD) Framework (ExecPlan)
This ExecPlan is a living document. Keep Progress / Decision Log current.

## 最新タスク
- ガバナンスポリシーを `min_runs` / `required_steps` / 新しいゲート評価と連動させ、CIの `flow gate` を安定化（agdd/assets/policies/flow_governance.yaml, agdd/governance/gate.py, observability/summarize_runs.py）
- Flow Runner 環境スクリプトとレジストリリンタを追加し、CI での開発者体験と品質ガードを強化（tools/flowrunner_env.sh, tools/lint_registry.py）
- Typer CLI `run` コマンドが位置引数を受け付けなくなった回帰を修正し、オプション指定との両立を保証（agdd/cli.py, tests/test_cli.py）

## Purpose / Big Picture
Establish the minimal AG-Driven Development (AGDD) repository skeleton so future AG-Driven Development (AGDD) work starts from a compliant baseline.

## To-do
- Document upgrade path for alternate runner adapters (Temporal, LangGraph, etc.)
- Establish release cadence for updating mirrored Flow Runner assets and schemas
- Expand policy coverage (skill manifests, security posture) ahead of scaling agent catalog

## Progress
- Baseline repository skeleton established with uv tooling, initial directories, and documentation
- Walking skeleton (registry -> contract validation -> skill execution) operational with tests and docs
- Runner abstraction landed with Flow Runner adapter, CLI, and mirrored assets
- Observability summary tooling in place for Flow Runner `.runs/`, including per-step metrics and MCP call counts
- Governance gate operational via `tools/gate_flow_summary.py` and CI enforcement
- CI workflow expanded with Flow Runner validation and Multi Agent Governance checks
- Packaging configuration ensures bundled assets ship with the wheel and includes smoke-test guidance

## Surprises & Discoveries
None so far.

## Decision Log
- Commit to an AI & AI Agent-first walking skeleton before expanding feature depth

## Outcomes & Retrospective
Framework deliverables are in place with passing tests and policy checks, ready for initial review and iteration.

## Context and Orientation
Work performed inside freshly initialized `agdd` repository under feature branch `feat/bootstrap-agdd`.

## Plan of Work
Deliver an executable path from registry lookup through skill invocation with schema validation, then harden supporting tooling and documentation so additional agents follow the same AG-first spine.

## Concrete Steps
1. Publish guidance for integrating new runner adapters alongside Flow Runner
2. Define process for syncing Flow Runner sample assets and schemas when upstream tags change
3. Broaden governance playbooks to include skill manifests and security checks

## Validation & Acceptance
Acceptance now includes passing Flow Runner CLI smoke tests (validate/run/summarize), documentation guardrails, pytest suite, and CI jobs (core, flowrunner, governance).
