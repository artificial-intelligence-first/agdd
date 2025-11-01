---
title: Skill Development Cheatsheet
slug: skills
status: living
last_synced: 2025-10-30
tags: [magsag, skills]
description: "Lean checklist for defining, implementing, and shipping MAGSAG skills."
source_of_truth: "https://github.com/artificial-intelligence-first/magsag"
---

# Skill Development Cheatsheet

This cheatsheet keeps skill development consistent without forcing you to read
pages of prose. Link out to detailed guides when further context is needed.

## Where Things Live

- Registry: `catalog/registry/skills.yaml`
- Implementation: `catalog/skills/<slug>/code/`
- Optional docs/resources: `catalog/skills/<slug>/SKILL.md`, `templates/`, `schemas/`

## Definition Checklist

1. Choose a canonical `id` (`skill.<slug>`) and append semantic versions.
2. Point `entrypoint` to the callable (`catalog/skills/.../code/main.py:run`).
3. Declare permissions; use the narrowest scope (e.g., `[]`, `["mcp:filesystem.read"]`).
4. Provide a short description or tags if discoverability matters.

## Implementation Notes

- Preferred signature:
  ```python
  async def run(payload: dict[str, Any], *, mcp: MCPRuntime | None = None) -> dict[str, Any]:
      ...
  ```
- Validate inputs explicitly (JSON Schema or manual guards).
- Handle `mcp is None` gracefully; log a warning and return a deterministic fallback.
- Keep functions pure and avoid global state. Read configuration from payload or
  `MAGSAG_` environment variables that are documented elsewhere.

## Testing

```bash
uv run pytest tests/skills/test_<skill>.py
uv run pytest tests/mcp/test_skill_mcp_integration.py   # when MCP involved
uv run mypy catalog/skills/<slug>/code
```

Cover:
- Success and failure paths.
- MCP-enabled and MCP-disabled scenarios.
- Contract compliance (return type matches calling agent expectations).

## Documentation & Release

- Update per-skill `SKILL.md` with purpose, inputs, outputs, and fallbacks.
- Cross-link new terminology in `docs/architecture/ssot.md` when needed.
- Add changelog entries for behaviour changes.
- Bump the registry version when modifying inputs, outputs, or side effects.

## References

- `docs/guides/mcp-integration.md` – full MCP server/client walkthrough.
- `catalog/skills/salary-band-lookup/` – async skill with MCP integration.
- `tests/mcp/` – integration tests demonstrating mocked transports.

Keep this cheatsheet lean. If you find yourself adding long explanations, move
them into the relevant guide and link back instead.
