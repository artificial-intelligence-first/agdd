# ExecPlans Directory

This directory contains Execution Plans (ExecPlans) for the AGDD project. ExecPlans are structured documents serving as the single source of truth for complex, multi-step development initiatives.

## Directory Structure

```
execplans/
├── README.md              # This file
├── template.md            # Standard ExecPlan template
├── active/                # In-progress plans
│   └── (active plans here)
├── completed/             # Successfully finished plans (archived by month)
│   ├── 2025-10/
│   └── 2025-09/
└── abandoned/             # Discontinued plans with reasons
    └── (abandoned plans here)
```

## Quick Start

### Creating a New ExecPlan

1. Copy the template:
   ```bash
   cp collab/execplans/template.md collab/execplans/active/feature-my-feature.md
   ```

2. Fill in the required sections:
   - Purpose / Big Picture
   - To-do list
   - Context and Orientation

3. Commit and push:
   ```bash
   git add collab/execplans/active/feature-my-feature.md
   git commit -m "docs(plans): initiate feature-my-feature ExecPlan"
   git push
   ```

### Working on an ExecPlan

Update the plan continuously as you work:
- Check off To-dos as completed
- Add Progress entries with timestamps (UTC)
- Document Surprises and Discoveries immediately
- Record all major Decisions with rationale

### Completing an ExecPlan

1. Complete the Outcomes & Retrospective section
2. Update CHANGELOG.md with user-facing changes
3. Move to completed/ directory:
   ```bash
   mkdir -p collab/execplans/completed/$(date +%Y-%m)
   git mv collab/execplans/active/feature-my-feature.md \
          collab/execplans/completed/$(date +%Y-%m)/
   git commit -m "docs(plans): complete feature-my-feature ExecPlan"
   ```

## Active Plans

*(No active plans at this time)*

## Recently Completed

### October 2025
- MCP Server Provider implementation
- HTTP API Phase 1 (authentication, rate limiting)
- Storage layer abstraction

## Guidelines

See [PLANS.md](../../PLANS.md) for complete governance and best practices.

### When to Create an ExecPlan
- Work spanning multiple hours or sessions
- Tasks involving multiple milestones or phases
- Multi-agent or human collaboration
- Decisions requiring traceability
- Complex work needing context restoration

### When NOT to Create an ExecPlan
- Simple bug fixes (< 1 hour)
- Single-file changes
- Trivial refactoring
- Documentation-only updates

## Naming Convention

Use kebab-case with descriptive prefixes:
- `feature-{name}.md` - New features
- `refactor-{component}.md` - Refactoring
- `fix-{bug}.md` - Complex bug fixes
- `spike-{topic}.md` - Research/investigation

Examples:
- `feature-github-integration.md`
- `refactor-agent-runner.md`
- `fix-rate-limiter-redis.md`
- `spike-cost-optimization.md`

## Integration

### With AGENTS.md
Reference standing procedures from AGENTS.md for testing, linting, and PR requirements.

### With CHANGELOG.md
After completing an ExecPlan, distill user-facing changes into CHANGELOG.md entries.

### With SSOT.md
Use SSOT terminology consistently throughout ExecPlans. Introduce new concepts to SSOT when discovered.

## Questions?

- See [PLANS.md](../../PLANS.md) for detailed guidance
- See [SSOT repository](https://github.com/artificial-intelligence-first/ssot/blob/main/files/PLANS.md) for canonical ExecPlan format
- Open an issue with the `documentation` label
