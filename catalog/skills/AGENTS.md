# AGENTS.md - Skill Development Guide

Operational guidance for developing reusable skills in the AGDD framework. Skills are stateless, composable functions that agents invoke to perform specific capabilities.

> **Parent Guide**: See [root AGENTS.md](../AGENTS.md) for project-wide development procedures.

## Dev Environment Tips

### Quick Setup for Skill Development

- **Test an existing skill** to verify your environment:
  ```bash
  # Skills are invoked through agents or the skill runtime
  echo '{"role":"Engineer","level":"Mid"}' | uv run agdd agent run offer-orchestrator-mag
  # This tests skills used by the orchestrator (e.g., task-decomposition)
  ```

- **Use skill template** for rapid development:
  ```bash
  cp -r skills/_template skills/your-skill-name
  ```
  Template includes: skill descriptor, implementation structure, and tests

- **Navigate skill structure**:
  ```
  skills/
  ├── _template/               # Skill template
  └── your-skill-name/
      ├── skill.yaml           # Skill metadata (optional, deprecated)
      ├── impl/
      │   └── your_skill.py    # Implementation (run function)
      ├── tests/
      │   └── test_skill.py    # Unit tests
      └── README.md            # Documentation
  ```

### Skill Design Principles

**1. Stateless**: Skills must not maintain state between invocations
- No global variables
- No file system persistence
- All state passed via input parameters

**2. Pure Functions**: Skills should be deterministic when possible
- Same input → same output (except for external API calls)
- Minimize side effects
- Use dependency injection for external services

**3. Composable**: Skills can invoke other skills
- Use the `skills` runtime provided to your skill's `run()` function
- Chain skills to build complex capabilities
- Avoid circular dependencies

**4. Contract-Driven**: Define clear input/output schemas
- Use type hints in Python
- Document expected input structure in README
- Validate inputs at skill boundaries

### Registry Integration

Skills are registered in `registry/skills.yaml`:

```yaml
skills:
  - id: "skill.your-skill-name"
    version: "0.1.0"
    location: "skills/your-skill-name"
    entrypoint: "skills/your-skill-name/impl/your_skill.py:run"
    permissions: []  # Optional: MCP permissions like "mcp:pg-readonly"
```

**Skill ID format**: `skill.<name>` (e.g., `skill.task-decomposition`)

**Entrypoint format**: `<path>:<function>` where function signature is:
```python
def run(payload: dict, *, skills=None, **kwargs) -> dict:
    """
    Args:
        payload: Input data (arbitrary structure)
        skills: SkillRuntime for invoking other skills (optional)
        **kwargs: Reserved for future extensions

    Returns:
        Output data (arbitrary structure)
    """
```

## Testing Instructions

### Unit Tests for Skills (`tests/unit/skills/`)

Skills should have comprehensive unit tests covering:

**Test checklist for new skills:**
- [ ] Valid input processing
- [ ] Invalid input handling (edge cases, malformed data)
- [ ] Output structure and types
- [ ] Error handling and exceptions
- [ ] Skill composition (if invoking other skills)
- [ ] Performance (if latency-sensitive)

**Example skill test:**
```python
def test_skill_with_valid_input():
    """Test skill execution with valid input"""
    from skills.your_skill.impl.your_skill import run

    result = run({"key": "value"})

    assert result is not None
    assert "expected_field" in result

def test_skill_with_invalid_input():
    """Test skill gracefully handles invalid input"""
    from skills.your_skill.impl.your_skill import run

    with pytest.raises(ValueError):
        run({"invalid": "input"})
```

**Run skill tests:**
```bash
# All skill unit tests
uv run -m pytest tests/unit/skills/ -v

# Specific skill
uv run -m pytest tests/unit/skills/test_your_skill.py -v
```

### Integration Testing via Agents

Test skills in context by:
1. Creating an agent that uses the skill
2. Testing the agent workflow in `tests/agents/`
3. Verifying skill invocation in observability logs

**Example:**
```bash
# Run agent test that uses your skill
uv run -m pytest tests/agents/test_agent_using_your_skill.py -v

# Check skill was invoked
cat .runs/agents/<RUN_ID>/logs.jsonl | grep your-skill-name
```

### Manual Validation

After implementing a skill:

1. **Test in isolation** via Python REPL:
   ```python
   from skills.your_skill.impl.your_skill import run

   result = run({"test": "input"})
   print(result)
   ```

2. **Test via agent** that uses the skill:
   ```bash
   echo '{"sample":"input"}' | uv run agdd agent run agent-using-skill
   ```

3. **Verify skill invocation** in logs:
   ```bash
   cat .runs/agents/<RUN_ID>/logs.jsonl | grep skill_invocation
   ```

## Creating New Skills

### Standard Skill Development

**Steps:**

1. **Copy template:**
   ```bash
   cp -r skills/_template skills/your-skill-name
   ```

2. **Implement `run()` function** in `impl/your_skill.py`:
   ```python
   from typing import Any, Dict

   def run(payload: Dict[str, Any], *, skills=None, **kwargs) -> Dict[str, Any]:
       """
       Skill implementation.

       Args:
           payload: Input data with fields:
               - field1: Description
               - field2: Description
           skills: SkillRuntime for invoking other skills (optional)
           **kwargs: Reserved for future extensions

       Returns:
           Output with structure:
               - result_field1: Description
               - result_field2: Description

       Raises:
           ValueError: If input validation fails
           RuntimeError: If skill execution fails
       """
       # Input validation
       if "required_field" not in payload:
           raise ValueError("Missing required_field in payload")

       # Skill logic
       result = process_input(payload)

       # Optional: Invoke other skills
       if skills and skills.exists("skill.other-skill"):
           sub_result = skills.invoke("skill.other-skill", {"data": result})
           result = merge_results(result, sub_result)

       # Return output
       return {
           "result_field1": result,
           "status": "success"
       }
   ```

3. **Update `README.md`** with:
   - Skill purpose and use cases
   - Input/output structure documentation
   - Example usage
   - Dependencies and permissions

4. **Register in `registry/skills.yaml`:**
   ```yaml
   skills:
     - id: "skill.your-skill-name"
       version: "0.1.0"
       location: "skills/your-skill-name"
       entrypoint: "skills/your-skill-name/impl/your_skill.py:run"
       permissions: []  # Add if skill needs MCP access
   ```

5. **Add unit tests** in `tests/unit/skills/test_your_skill.py`

6. **Optional: Add to agent dependencies** in agent's `agent.yaml`:
   ```yaml
   dependencies:
     skills:
       - skill.your-skill-name
   ```

### Skill Composition Pattern

For complex skills, compose smaller skills:

```python
def run(payload: Dict[str, Any], *, skills=None, **kwargs) -> Dict[str, Any]:
    """Composite skill that orchestrates multiple sub-skills"""

    # Step 1: Use skill A
    if skills and skills.exists("skill.skill-a"):
        step1_result = skills.invoke("skill.skill-a", payload)
    else:
        step1_result = fallback_logic_a(payload)

    # Step 2: Use skill B with step 1 output
    if skills and skills.exists("skill.skill-b"):
        step2_result = skills.invoke("skill.skill-b", step1_result)
    else:
        step2_result = fallback_logic_b(step1_result)

    # Combine results
    return {
        "step1": step1_result,
        "step2": step2_result,
        "combined": merge(step1_result, step2_result)
    }
```

## Build & Deployment

- Skills are deployed as part of the `agdd` package
- Verify skill is registered:
  ```bash
  grep "skill.your-skill-name" registry/skills.yaml
  ```
- Ensure skill entrypoint is importable:
  ```bash
  uv run python -c "from skills.your_skill.impl.your_skill import run; print('OK')"
  ```

## Linting & Code Quality

- Run linting on skill code:
  ```bash
  uv run ruff check skills/
  ```

- Type-check skill implementations:
  ```bash
  uv run mypy skills/
  ```

- Ensure stateless design:
  - No global variables
  - No file I/O without explicit parameters
  - No class instance state

## PR Instructions for Skill Changes

When submitting PRs that add or modify skills:

1. **Update documentation:**
   - [ ] Skill `README.md` describes purpose and I/O structure
   - [ ] Root `CHANGELOG.md` includes skill changes under `[Unreleased]`
   - [ ] Docstrings in `run()` function are complete

2. **Ensure test coverage:**
   - [ ] Unit tests cover valid/invalid inputs
   - [ ] Edge cases are tested
   - [ ] All tests pass: `uv run -m pytest -q`

3. **Verify registry integration:**
   - [ ] Skill registered in `registry/skills.yaml`
   - [ ] Entrypoint is correct and importable
   - [ ] Permissions are documented (if using MCP)

4. **Include usage example in PR description:**
   ```python
   from skills.your_skill.impl.your_skill import run
   result = run({"sample": "input"})
   # Expected output: {"result": "..."}
   ```

## Security & Credentials

- Skills should **never** hardcode credentials or API keys
- Use permissions in `registry/skills.yaml` to declare MCP access:
  ```yaml
  permissions:
    - "mcp:pg-readonly"    # Read-only PostgreSQL access
    - "mcp:api-client"     # External API client
  ```
- Validate all inputs to prevent injection attacks
- Sanitize outputs before returning (avoid leaking sensitive data)
- Log skill invocations carefully - avoid PII in logs

## Troubleshooting

### Skill not found in registry
```bash
# Verify registration
grep "skill.your-skill-name" registry/skills.yaml

# Check entrypoint path
ls -la skills/your-skill-name/impl/your_skill.py
```

### Import errors
```bash
# Test import directly
uv run python -c "from skills.your_skill.impl.your_skill import run; print('OK')"

# Check Python path includes project root
cd /home/user/agdd
uv run python -c "import sys; print(sys.path)"
```

### Skill invocation failures
```bash
# Check agent logs for skill errors
cat .runs/agents/<RUN_ID>/logs.jsonl | grep skill_error

# Test skill in isolation
uv run python -c "
from skills.your_skill.impl.your_skill import run
try:
    result = run({'test': 'input'})
    print('Success:', result)
except Exception as e:
    print('Error:', e)
"
```

### Skill runtime not available
If `skills` parameter is `None` in your skill:
- Check that the skill is invoked via an agent or skill runtime
- Direct invocation doesn't provide skill composition:
  ```python
  # Direct invocation - no skills runtime
  from skills.your_skill.impl.your_skill import run
  run(payload)  # skills=None

  # Via agent - skills runtime provided
  runner.invoke_sag(...)  # Agent's skills runtime passed to SAG's skills
  ```

## Further Resources

- [Root AGENTS.md](../AGENTS.md) - Project-wide development procedures
- [RUNNERS.md](../RUNNERS.md) - Skill runtime and invocation patterns
- [SSOT.md](../SSOT.md) - Terminology (MAG, SAG, Skill definitions)
- Skill template: `skills/_template/`
- Example skills: `skills/task-decomposition/`, `skills/salary-band-lookup/`
