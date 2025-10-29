---
title: AGDD Changelog
slug: changelog
status: living
last_updated: 2025-10-30
tags: [agdd, changelog, releases, semver]
summary: "Release history for the AG-Driven Development framework following Keep a Changelog and SemVer."
sources:
  - { id: R1, title: "Keep a Changelog 1.1.0", url: "https://keepachangelog.com/en/1.1.0/", accessed: "2025-10-30" }
  - { id: R2, title: "Semantic Versioning 2.0.0", url: "https://semver.org/spec/v2.0.0.html", accessed: "2025-10-30" }
---

# Changelog

> **For Humans**: Track noteworthy AGDD changes here. Every entry explains user-facing impact, links to issues or docs, and follows SemVer semantics.
>
> **For AI Agents**: Update the `Unreleased` section whenever you ship a meaningful behaviour change. Do not create tagged releases without human approval.

## Overview

- Format: [Keep a Changelog][keepachangelog]
- Versioning: [Semantic Versioning][semver]
- Scope: CLI, API, runners, catalog assets, docs, and governance updates that affect project users.

[keepachangelog]: https://keepachangelog.com/en/1.1.0/
[semver]: https://semver.org/spec/v2.0.0.html

## How to Use This File

1. Append user-facing updates under `## [Unreleased]` with the correct category (`Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`).
2. When preparing a release, move curated entries into a new version section with an ISO 8601 date.
3. Update comparison links at the end of the file to keep GitHub diff references accurate.

## Release Notes

### [Unreleased]

#### Added
- Placeholder for upcoming changes.

### [0.1.0] - 2025-10-30

#### Added
- Initial public release of the AGDD framework with Typer CLI (`agdd`) covering flow, agent, data, and MCP commands.
- FastAPI HTTP API with custom error formatting, rate limiting hooks, and `/health` endpoint.
- Agent runner orchestrating MAG/SAG lifecycles, skill delegation, evaluation hooks, and observability logging.
- Catalog-driven assets for agents, skills, routing, governance, and evaluation metrics.
- Observability stack including JSONL + SQLite cost tracking, OpenTelemetry bootstrap, and run summarisation.

#### Changed
- Standardised repository documentation to align with SSOT templates (AGENTS, CONTRIBUTING, PLANS, README, SKILL, SSOT).

## Maintenance Notes

- Always include links to relevant issues/PRs where possible, e.g. `(#123)`.
- Document schema or policy changes that require downstream updates (docs, contracts, infrastructure).
- If a change is purely internal, mention it under `Changed` only when it affects contributor workflows.

## Links

- [Unreleased]: https://github.com/artificial-intelligence-first/agdd/compare/v0.1.0...HEAD
- [0.1.0]: https://github.com/artificial-intelligence-first/agdd/releases/tag/v0.1.0

## Update Log

- 2025-10-30: Established AGDD changelog with initial 0.1.0 entry.
