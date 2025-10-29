# PLANS.md: ExecPlans Governance

## Purpose

This document defines the governance, location, and lifecycle management for Execution Plans (ExecPlans) in the AGDD repository. ExecPlans are structured documents serving as the single source of truth for complex, multi-step development initiatives.

## ExecPlans Overview

ExecPlans enable:
- **Progress visibility**: Track work across multiple sessions and contributors
- **Decision documentation**: Record major decisions with rationale
- **Task resumption**: Any contributor can continue work using only the working tree and the plan
- **Collaboration**: Multiple agents and humans coordinate through shared documents
- **Auditability**: Complete history of work, surprises, and outcomes

## When to Create an ExecPlan

### ✓ Create ExecPlan for:
- Work spanning multiple hours or sessions
- Tasks involving multiple milestones or phases
- Multi-agent or human collaboration
- Decisions requiring traceability
- Complex work needing context restoration
- Features affecting multiple components
- Architectural changes or refactoring

### ✗ Do NOT create ExecPlan for:
- Simple bug fixes (single-file, < 1 hour)
- Trivial refactoring
- Documentation-only updates
- Single-file changes
- Routine maintenance

## Storage Location

All ExecPlans are stored in the `collab/execplans/` directory:

```
agdd/
└── collab/
    └── execplans/
        ├── README.md                    # This location's index
        ├── template.md                  # Standard ExecPlan template
        ├── active/                      # In-progress plans
        │   ├── feature-semantic-cache.md
        │   └── refactor-storage-layer.md
        ├── completed/                   # Archived completed plans
        │   ├── 2025-10/
        │   │   ├── api-auth-implementation.md
        │   │   └── mcp-server-provider.md
        │   └── 2025-09/
        └── abandoned/                   # Discontinued plans with context
            └── experimental-local-llm.md
```

### Directory Structure
- **active/**: Plans currently being worked on
- **completed/**: Successfully finished plans (archived by month)
- **abandoned/**: Discontinued plans with reasons and learnings

## Naming Convention

Use kebab-case with descriptive names:
- `feature-{capability-name}.md` - New features
- `refactor-{component-name}.md` - Refactoring efforts
- `fix-{bug-description}.md` - Complex bug fixes requiring planning
- `spike-{investigation-topic}.md` - Research and investigation

Examples:
- `feature-github-integration.md`
- `refactor-agent-runner.md`
- `fix-rate-limiter-redis.md`
- `spike-cost-optimization-strategies.md`

## Required Sections

Every ExecPlan must include these sections:

### 1. Purpose / Big Picture
- Why this work matters
- Problems being solved
- Success criteria
- Expected impact

### 2. To-do
- Actionable checkboxes organized by phase or priority
- Clear completion criteria
- Dependencies between tasks
- Format: `- [ ] Task description`

### 3. Progress
- Timestamped (UTC) updates of completed work
- Format: `YYYY-MM-DD HH:MM UTC - Action taken - Outcome`
- Updated immediately after significant actions
- Includes both successes and failures

### 4. Surprises & Discoveries
- Unexpected findings
- Blockers and workarounds
- Technical learnings
- Changed assumptions
- Format: Timestamped entries with context

### 5. Decision Log
- Major decisions with rationale
- Alternatives considered
- Actual outcomes
- Impact assessment
- Format: Decision → Rationale → Alternatives → Outcome

### 6. Outcomes & Retrospective
- Final results and deliverables
- Lessons learned
- Follow-up items
- What worked well / what didn't
- Completed only when closing the plan

### Optional Extended Sections
- **Context and Orientation**: Background information
- **Plan of Work**: High-level strategy and phases
- **Concrete Steps**: Detailed step-by-step instructions
- **Validation and Acceptance**: How to verify success
- **Idempotence and Recovery**: Retry and rollback procedures
- **Artifacts and Notes**: Links to related resources
- **Interfaces and Dependencies**: System boundaries and integrations

## Lifecycle Workflow

### 1. Initiate
```bash
# Copy template
cp collab/execplans/template.md collab/execplans/active/feature-my-feature.md

# Edit Purpose, Context, and initial To-do list
# Commit and push
git add collab/execplans/active/feature-my-feature.md
git commit -m "docs(plans): initiate feature-my-feature ExecPlan"
git push
```

### 2. Plan
- Outline phases and dependencies
- Define validation criteria
- Identify risks and mitigation strategies
- Update To-do with concrete steps

### 3. Operate
- Execute work following the plan
- Update Progress immediately after each significant action
- Document Surprises and Discoveries as they occur
- Record all major Decisions with rationale
- Check off To-dos as completed

### 4. Validate
- Verify success against acceptance criteria
- Run tests and validation procedures
- Document validation results

### 5. Close
- Complete Outcomes & Retrospective section
- Move to completed/ directory (organized by month)
- Update CHANGELOG.md with user-facing changes
- Link from relevant documentation

## Best Practices

### For All Contributors

**Real-time Updates**: Update the plan as you work, not in batches
- ✓ Good: Update Progress after each milestone
- ✗ Bad: Batch-update at end of day

**Specific Progress Entries**: Include timestamp, action, and outcome
- ✓ Good: `2025-10-29 14:30 UTC - Implemented Redis cache backend - Tests passing, 50ms latency`
- ✗ Bad: `Worked on cache stuff`

**Document Decisions**: Record rationale and alternatives
- ✓ Good: "Chose Redis over Memcached for persistence support. Alternatives: Memcached (faster but no persistence), In-memory (simplest but no distribution)"
- ✗ Bad: "Using Redis"

**Capture Surprises**: Note unexpected findings immediately
- ✓ Good: `2025-10-29 15:00 UTC - Discovered Redis Lua scripts required for atomic rate limiting. Original approach would have race conditions.`
- ✗ Bad: Forget to document and struggle with the same issue later

**Clear To-dos**: Use actionable language with completion criteria
- ✓ Good: `- [ ] Implement Redis cache backend with connection pooling (10 connections, 30s timeout)`
- ✗ Bad: `- [ ] Do cache thing`

### For AI Agents

1. **Check for existing ExecPlan** before starting complex work
2. **Create ExecPlan** if work will span multiple sessions
3. **Update Progress section** immediately after significant actions
4. **Document all decisions** with brief rationale
5. **Capture unexpected findings** with timestamps
6. **Check off To-dos** as completed (don't batch)
7. **Keep Concrete Steps current** as you learn
8. **Validate continuously** against acceptance criteria
9. **Request human review** for major decisions
10. **Complete retrospective** before closing plan

### For Human Reviewers

- Review Progress and Decisions during PR reviews
- Verify To-dos are completed before merging
- Check that Surprises are addressed or documented
- Ensure Validation criteria are met
- Approve plan closure and archival

## Integration with Other Conventions

### AGENTS.md
ExecPlans reference standing procedures from AGENTS.md:
- Testing commands and requirements
- Linting and formatting procedures
- PR workflow and commit conventions
- Security and credential management

### CHANGELOG.md
ExecPlans provide detailed implementation history; CHANGELOG.md distills user-facing impact:
- Complete ExecPlan: Write detailed CHANGELOG entry
- Archive ExecPlan: Verify CHANGELOG is updated

### SSOT.md
ExecPlans use SSOT terminology consistently:
- Reference SSOT definitions
- Introduce new concepts to SSOT when discovered
- Maintain terminology alignment

## Template

See `collab/execplans/template.md` for the standard ExecPlan template. Copy this template when creating new plans.

## Active ExecPlans

### Current Active Plans

*(No active plans at this time)*

### Recently Completed

- **2025-10-25**: MCP Server Provider implementation
- **2025-10-24**: HTTP API Phase 1 (authentication, rate limiting)
- **2025-10-23**: Storage layer abstraction

## Governance

### Review Frequency
- Active plans: Review weekly during team sync
- Completed plans: Retain indefinitely for historical reference
- Abandoned plans: Document reason and learnings before archival

### Quality Criteria
- [ ] Purpose clearly defined
- [ ] To-dos are actionable with completion criteria
- [ ] Progress entries include timestamps and outcomes
- [ ] Decisions include rationale and alternatives
- [ ] Surprises are documented with context
- [ ] Validation criteria are specified
- [ ] Retrospective completed before archival

### Compliance
- ExecPlans are required for work tracked in project management tools
- Plans must be updated in real-time (not batch-updated)
- Completed plans must be archived within 7 days of completion
- CHANGELOG.md must be updated when archiving plans

## Common Patterns

### Parallel Implementation
```markdown
## To-do

### Phase 1: Foundation (Parallel)
- [ ] Implement cache interface
- [ ] Implement storage backend
- [ ] Implement API endpoints

### Phase 2: Integration (Sequential)
- [ ] Integrate cache with API
- [ ] Add observability hooks
- [ ] Deploy to staging
```

### Blocked Tasks
```markdown
## To-do
- [ ] ⏸️ BLOCKED: Implement feature X (waiting for upstream API release)
- [ ] In Progress: Work on feature Y (can proceed independently)

## Surprises & Discoveries
2025-10-29 14:00 UTC - Discovered upstream API v2 required for feature X. Current v1 lacks necessary endpoints. Estimated release: 2 weeks. Workaround: Mock API for development.
```

### Spike Milestones
```markdown
## To-do

### Spike Phase (Research)
- [ ] Evaluate Redis vs Memcached performance
- [ ] Prototype both approaches
- [ ] Document findings and recommendation

### Decision Point
- [ ] Choose cache backend based on spike results

### Implementation Phase (After decision)
- [ ] Implement chosen backend
- [ ] Add tests
- [ ] Deploy
```

## Questions?

For questions about ExecPlans or this governance document:
- See detailed guide: https://github.com/artificial-intelligence-first/ssot/blob/main/files/PLANS.md
- Open an issue with the `documentation` label
- Ask in team chat

---

**Last Updated**: 2025-10-29
**Maintained By**: AGDD Core Team
**Changes**: See CHANGELOG.md for document revision history
