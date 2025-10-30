---
title: AGDD Skill Development Guide
slug: skill
status: living
last_synced: 2025-10-30
tags: [agdd, skills, mcp, catalog, development]
description: "Standards for building, documenting, and validating skills in the AG-Driven Development framework."
source_of_truth: "https://github.com/artificial-intelligence-first/agdd"
sources:
  - { id: R1, title: "Skill Registry", url: "catalog/registry/skills.yaml", accessed: "2025-10-30" }
  - { id: R2, title: "Skill Runtime", url: "src/agdd/runners/agent_runner.py", accessed: "2025-10-30" }
  - { id: R3, title: "MCP Integration Guide", url: "../guides/mcp-integration.md", accessed: "2025-10-30" }
---

# AGDD Skill Development Guide (SKILL.md)

> **For Humans**: Use this handbook when creating or updating skills consumed by AGDD agents. It explains metadata requirements, MCP integration, testing, and documentation expectations.
>
> **For AI Agents**: Follow every checklist. Validate schemas, bump versions, update documentation, and respect MCP permissions.

## Overview

Skills are reusable capabilities that MAG/SAG agents invoke through the `SkillRuntime`. Each skill combines metadata, implementation code, and optional resources.

**Key facts**
- Registry entries live in `catalog/registry/skills.yaml`.
- Implementation modules reside in `catalog/skills/<slug>/code/`.
- Optional resources (prompts, schemas, templates) live beside the code.
- Skills may run synchronously or asynchronously; MCP-enabled skills must be async.

## Directory Layout

```
catalog/
└── skills/
    ├── <skill-slug>/
    │   ├── skill.yaml           # Optional skill-specific metadata
    │   ├── SKILL.md             # Optional human-facing note for the skill
    │   └── code/
    │       └── main.py          # Entrypoint referenced by registry
    └── ...
```

## Registry Requirements

Add or update entries in `catalog/registry/skills.yaml` with:

- `id`: Canonical identifier, e.g. `skill.salary-band-lookup`.
- `version`: Semantic Versioning. Bump on behaviour or signature change.
- `entrypoint`: Relative module path with callable (`catalog/skills/.../code/main.py:run`).
- `permissions`: List of granted capabilities (`mcp:pg-readonly`, etc.). Use empty list for local-only skills.
- Optional metadata (description, tags) may be added in `skill.yaml` if needed by downstream tooling.

## Implementation Standards

- Function signature:
  ```python
  async def run(payload: dict[str, Any], *, mcp: MCPRuntime | None = None) -> dict[str, Any]:
      ...
  ```
  - Synchronous skills may exist for legacy reasons but should migrate to async when MCP support is required.
  - Always accept `mcp` as a keyword-only parameter to enable runtime injection.
- Validate inputs before processing. Use JSON Schema or manual guards. Example:
  ```python
  from agdd.skills.base import SkillBase
  SkillBase.validate_payload(payload, INPUT_SCHEMA, "candidate_profile")
  ```
- Handle MCP unavailability gracefully (`mcp is None`). Provide deterministic fallbacks and log warnings.
- Return structured dictionaries that conform to contracts referenced by the invoking agent (see `SSOT.md`).
- Avoid global mutable state; any configuration belongs in payload or environment variables documented in `SSOT.md`.

## MCP Integration

- Declare permissions in the registry entry. Prefix with `mcp:` and scope narrowly (e.g., `mcp:filesystem.read`).
- Runtime behaviour:
  - `SkillRuntime` lazily starts MCP servers on first use.
  - The `mcp` argument exposes helpers such as `query_postgres`, `execute_tool`, or provider-specific clients.
- Expectation for MCP-enabled skills:
  - Validate runtime availability (`if not mcp: fallback`).
  - Enforce access controls before calling remote tools.
  - Document behaviour in the skill’s local `SKILL.md` and note dependencies in `SSOT.md`.

## Testing Guidelines

| Scenario | Command |
|----------|---------|
| Unit tests | `uv run -m pytest tests/skills/test_<skill>.py` |
| Integration (MCP) | `uv run -m pytest tests/mcp/test_skill_mcp_integration.py` |
| Async validation | Use `pytest.mark.asyncio` and cover success/failure branches |
| Type checking | `uv run mypy catalog/skills/<skill>/code` |
| Catalog validation | Covered by pytest (catalog tests validate schemas). |

Testing checklist:
- Cover both MCP-present and MCP-absent paths.
- Include contract validation tests where schemas apply.
- Mock external services; do not depend on live endpoints.

## Documentation Expectations

- Update this file when conventions or tooling change.
- Provide per-skill notes in `catalog/skills/<skill>/SKILL.md` (purpose, inputs, outputs, fallback behaviour).
- Cross-link to `SSOT.md` when introducing new terminology or contracts.
- Reflect changes in `CHANGELOG.md` under `Added`/`Changed` sections.

## Release Checklist

1. Update registry entry with new version and permissions.
2. Implement code changes and ensure tests pass.
3. Update documentation (`SKILL.md`, per-skill docs, SSOT).
4. Add changelog entry.
5. If part of a broader initiative, update the corresponding ExecPlan.

## Reference Material

- `catalog/skills/task-decomposition/` – sync legacy skill example.
- `catalog/skills/salary-band-lookup/` – async MCP-enabled example with graceful fallback.
- `tests/skills/` – unit tests demonstrating invocation patterns.
- `docs/guides/mcp-integration.md` – detailed MCP server/client setup.

## Update Log

- 2025-10-30: Rebuilt SKILL guide with async + MCP standards and testing guidance.
