# AGENTS.md - Agent Development Guide

Operational guidance for developing MAG (Main Agent) and SAG (Sub-Agent) implementations in the AGDD framework. This guide focuses on agent-specific workflows, testing, and best practices.

> **Parent Guide**: See [root AGENTS.md](../AGENTS.md) for project-wide development procedures.

## Dev Environment Tips

### Quick Setup for Agent Development

- **Test an existing agent** to verify your environment:
  ```bash
  echo '{"role":"Engineer","level":"Mid"}' | uv run agdd agent run offer-orchestrator-mag
  ```
  This validates the registry, agent runner, contracts, and skills integration.

- **Use agent templates** for rapid development:
  - **MAG Template**: `agents/_template/mag-template/` - For orchestration agents
  - **SAG Template**: `agents/_template/sag-template/` - For specialist agents
  - Each template includes: `agent.yaml`, implementation code, README, and ROUTE.md

- **Navigate agent structure**:
  ```
  agents/
  ├── main/                    # Main Agents (orchestrators)
  │   └── <name>-mag/
  │       ├── agent.yaml       # Agent metadata and contracts
  │       ├── code/            # Implementation (orchestrator.py)
  │       ├── README.md        # Human-facing documentation
  │       └── ROUTE.md         # Decision logic and task routing
  └── sub/                     # Sub-Agents (specialists)
      └── <name>-sag/
          ├── agent.yaml       # Agent metadata and contracts
          ├── code/            # Implementation (advisor.py)
          └── README.md        # Purpose and contracts
  ```

- **Agent naming convention**:
  - MAG: Use suffix `-mag` (e.g., `offer-orchestrator-mag`)
  - SAG: Use suffix `-sag` (e.g., `compensation-advisor-sag`)
  - Slug format: lowercase with hyphens

### Contract Schema Development

- Define input/output schemas in `contracts/` using JSON Schema (Draft 7)
- Reference schemas in `agent.yaml` under `input_contract` and `output_contract`
- Validate schemas with contract tests:
  ```bash
  uv run -m pytest tests/contract/ -v
  ```

### Registry Integration

- **Register agents** in `registry/agents.yaml` for task routing:
  ```yaml
  agents:
    - slug: your-orchestrator-mag
      path: agents/main/your-orchestrator-mag
      tasks:
        - "generate employment offer"
        - "create compensation package"
  ```

- **Verify registration**:
  ```bash
  uv run agdd agent run your-orchestrator-mag --json examples/sample_input.json
  ```

## Testing Instructions

### Agent Test Layer (`tests/agents/`)

Agent tests validate MAG/SAG behavior with contract compliance and error handling.

**Test checklist for new agents:**
- [ ] Input contract validation (valid and invalid inputs)
- [ ] Output contract validation (schema compliance)
- [ ] Observability artifacts (logs.jsonl, metrics.json, summary.json)
- [ ] Fallback logic (partial failures, SAG errors)
- [ ] Edge cases (empty inputs, missing fields, boundary values)

**Example agent test structure:**
```python
def test_agent_with_valid_input(tmp_path):
    """Test agent execution with valid contract input"""
    # Setup input conforming to contract schema
    # Execute agent via runner
    # Assert output matches contract schema
    # Verify observability artifacts exist

def test_agent_fallback_on_sag_failure(tmp_path):
    """Test MAG fallback when SAG delegations fail"""
    # Mock SAG to return error
    # Execute MAG
    # Assert graceful degradation or error handling
```

**Run agent tests:**
```bash
# All agent tests
uv run -m pytest tests/agents/ -v

# Specific agent
uv run -m pytest tests/agents/test_offer_orchestrator_mag.py -v

# With observability artifact inspection
uv run -m pytest tests/agents/ -v -s
```

### Integration Testing

When adding new agents, ensure E2E integration tests cover:
- Full MAG→SAG orchestration workflow
- CLI invocation via `agdd agent run`
- Observability artifact generation in `.runs/agents/<RUN_ID>/`

**Example:**
```bash
uv run -m pytest tests/integration/test_e2e_offer_workflow.py -v
```

### Manual Validation

After implementing an agent:

1. **Execute with sample input:**
   ```bash
   echo '{"role":"Senior Engineer","level":"Senior","experience_years":8}' | \
     uv run agdd agent run your-orchestrator-mag
   ```

2. **Inspect observability artifacts:**
   ```bash
   ls -la .runs/agents/mag-<RUN_ID>/
   cat .runs/agents/mag-<RUN_ID>/logs.jsonl
   jq . .runs/agents/mag-<RUN_ID>/metrics.json
   ```

3. **Verify logs contain required events:**
   - `start` - Agent execution begins
   - `delegation_start` / `delegation_complete` - SAG invocations
   - `end` - Agent execution completes

4. **Check metrics meet SLO targets:**
   - Success rate: ≥95% for MAG, ≥98% for SAG
   - P95 latency: ≤5s for MAG, ≤2s for SAG

## Creating New Agents

### MAG (Main Agent) Development

**Purpose**: Orchestrate workflows by decomposing tasks and delegating to SAGs.

**Steps:**

1. **Copy template:**
   ```bash
   cp -r agents/_template/mag-template agents/main/your-orchestrator-mag
   ```

2. **Customize `agent.yaml`:**
   ```yaml
   slug: your-orchestrator-mag
   name: Your Orchestrator MAG
   description: Orchestrates [specific workflow]
   type: mag
   version: "1.0.0"
   input_contract: contracts/your_input.schema.json
   output_contract: contracts/your_output.schema.json
   dependencies:
     sags:
       - your-advisor-sag
     skills:
       - skill.task-decomposition  # Optional
   ```

3. **Implement orchestration logic** in `code/orchestrator.py`:
   - Phase 1: Task decomposition (optional skill invocation)
   - Phase 2: SAG delegation via `runner.invoke_sag()`
   - Phase 3: Result aggregation and output generation
   - Use `obs.log()` and `obs.metric()` for observability

4. **Update `ROUTE.md`** with decision logic and task routing rules

5. **Update `README.md`** with agent purpose, contracts, and usage examples

6. **Register in `registry/agents.yaml`:**
   ```yaml
   agents:
     - slug: your-orchestrator-mag
       path: agents/main/your-orchestrator-mag
       tasks:
         - "your task description"
   ```

7. **Add tests** in `tests/agents/test_your_orchestrator_mag.py`

### SAG (Sub-Agent) Development

**Purpose**: Execute specialized domain tasks with strict contract compliance.

**Steps:**

1. **Copy template:**
   ```bash
   cp -r agents/_template/sag-template agents/sub/your-advisor-sag
   ```

2. **Customize `agent.yaml`:**
   ```yaml
   slug: your-advisor-sag
   name: Your Advisor SAG
   description: Provides [specific domain expertise]
   type: sag
   version: "1.0.0"
   input_contract: contracts/your_sag_input.schema.json
   output_contract: contracts/your_sag_output.schema.json
   skills:
     - skill.your-domain-skill  # Optional
   ```

3. **Implement domain logic** in `code/advisor.py`:
   - Validate inputs strictly against contract
   - Use skills for reusable logic via `skills.invoke()`
   - Return output conforming to contract schema
   - Handle errors gracefully with fallback logic

4. **Update `README.md`** with SAG purpose and contract details

5. **Add tests** in `tests/agents/test_your_advisor_sag.py`

## Build & Deployment

- Agents are deployed as part of the `agdd` package distribution
- Verify agent metadata is valid:
  ```bash
  uv run agdd agent run your-agent-slug --help
  ```
- Ensure agent contracts are bundled in `contracts/`

## Linting & Code Quality

- Run linting on agent code:
  ```bash
  uv run ruff check agents/
  ```

- Type-check agent implementations:
  ```bash
  uv run mypy agents/
  ```

- Validate contract schemas:
  ```bash
  uv run -m pytest tests/contract/ -v
  ```

## PR Instructions for Agent Changes

When submitting PRs that add or modify agents:

1. **Update documentation:**
   - [ ] Agent `README.md` describes purpose and contracts
   - [ ] MAG `ROUTE.md` documents decision logic (if applicable)
   - [ ] Root `CHANGELOG.md` includes agent changes under `[Unreleased]`

2. **Ensure test coverage:**
   - [ ] Agent tests validate contracts and observability
   - [ ] Integration tests cover E2E workflow
   - [ ] All tests pass: `uv run -m pytest -q`

3. **Verify registry integration:**
   - [ ] Agent registered in `registry/agents.yaml`
   - [ ] Task routing works: `uv run agdd agent run <slug>`

4. **Include sample execution in PR description:**
   ```bash
   echo '{"sample":"input"}' | uv run agdd agent run your-agent-slug
   ```
   Paste observability summary from `.runs/agents/<RUN_ID>/summary.json`

## Security & Credentials

- Agents should **never** hardcode credentials or API keys
- Use environment variables for external service authentication
- Validate all inputs against contract schemas to prevent injection attacks
- Log sensitive data carefully - avoid exposing PII in observability artifacts
- Review SAG outputs before logging to ensure compliance with data policies

## Troubleshooting

### Agent not found in registry
```bash
# Verify registration
grep "your-agent-slug" registry/agents.yaml

# Check file path
ls -la agents/main/your-agent-slug/agent.yaml
```

### Contract validation errors
```bash
# Validate schema syntax
uv run -m pytest tests/contract/ -v

# Check input/output conform to schema
uv run python -c "import jsonschema, json; \
  jsonschema.validate(json.load(open('input.json')), \
  json.load(open('contracts/your_input.schema.json')))"
```

### SAG delegation failures
```bash
# Check SAG is registered
grep "your-sag-slug" registry/agents.yaml

# Verify SAG agent.yaml exists
ls -la agents/sub/your-sag-slug/agent.yaml

# Check delegation logs
cat .runs/agents/<RUN_ID>/logs.jsonl | grep delegation_error
```

## Further Resources

- [Root AGENTS.md](../AGENTS.md) - Project-wide development procedures
- [RUNNERS.md](../RUNNERS.md) - Agent runner capabilities and observability
- [SSOT.md](../SSOT.md) - Terminology and canonical definitions
- Agent templates: `agents/_template/mag-template/`, `agents/_template/sag-template/`
