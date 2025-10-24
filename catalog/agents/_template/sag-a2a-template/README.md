# YourA2AAdvisorSAG

**Role:** Sub-Agent (SAG) with A2A Support
**Version:** 0.1.0
**Status:** Template

## Overview

This is an A2A-enabled (Agent-to-Agent) specialist template that supports:
- **Discovery:** Can be discovered by other agents via API
- **Invocation:** Can be invoked by MAGs via runner or API
- **Context Propagation:** Preserves A2A tracing context
- **Specialized Processing:** Executes domain-specific tasks

## A2A Capabilities

### Discovery
This agent can be discovered via the agent registry:
```bash
curl http://localhost:8000/api/v1/agents
```

Response includes:
```json
{
  "slug": "your-a2a-advisor-sag",
  "title": "YourA2AAdvisorSAG",
  "description": "A2A-enabled Sub-Agent for specialized task execution"
}
```

### Invocation
This agent is typically invoked by MAGs via the runner interface, but can also be called via API if needed:

#### Via Runner (Standard)
```python
delegation = Delegation(
    task_id="task-1",
    sag_id="your-a2a-advisor-sag",
    input=task_input,
    context={
        "parent_run_id": "mag-abc123",
        "correlation_id": "xyz-789"
    }
)
result = runner.invoke_sag(delegation)
```

#### Via API (Advanced)
```bash
curl -X POST http://localhost:8000/api/v1/agents/your-a2a-advisor-sag/run \
  -H "Content-Type: application/json" \
  -d '{"domain_field": "value", "context": {"correlation_id": "xyz-789"}}'
```

## Responsibilities

- Execute domain-specific logic
- Preserve A2A context for tracing
- Return structured output conforming to contract
- Handle errors gracefully with meaningful messages

## Input Contract

**Schema:** `contracts/a2a_advisor_input.schema.json`

Example:
```json
{
  "domain_field": "value",
  "parameters": {
    "param1": 123,
    "param2": "option_a"
  },
  "context": {
    "parent_run_id": "mag-abc123",
    "correlation_id": "xyz-789",
    "source_agent": "your-a2a-orchestrator-mag",
    "call_chain": ["external-client", "your-a2a-orchestrator-mag"]
  }
}
```

## Output Contract

**Schema:** `contracts/a2a_advisor_output.schema.json`

Example:
```json
{
  "result": {
    "processed_field": "processed_value",
    "details": {
      "metric1": 42,
      "metric2": "status_ok"
    }
  },
  "confidence": 0.95,
  "notes": "Processed successfully",
  "trace": {
    "correlation_id": "xyz-789",
    "processing_time_ms": 150,
    "call_depth": 2
  }
}
```

## Dependencies

### Skills
- `skill.your-domain-skill` - Domain-specific processing skill

## Execution Logic

1. **Input Extraction** - Extract data and A2A context
2. **Context Validation** - Verify A2A tracing context
3. **Domain Processing** - Apply specialized logic
4. **Skill Invocation** - Call required skills
5. **Output Formatting** - Package results with A2A trace

## A2A Context Handling

### Context Extraction
```python
# Extract A2A context from payload
a2a_context = payload.get("context", {})
correlation_id = a2a_context.get("correlation_id")
parent_run_id = a2a_context.get("parent_run_id")
call_chain = a2a_context.get("call_chain", [])
```

### Context Propagation
```python
# Preserve context in output
output_trace = {
    "correlation_id": correlation_id,
    "processing_time_ms": duration_ms,
    "call_depth": len(call_chain),
    "parent_run_id": parent_run_id,
}
```

## Error Handling

- **Invalid Input:** Return error with validation details
- **Skill Failure:** Log error and return partial/default result
- **Context Missing:** Log warning, continue with degraded tracing
- **Unexpected Exception:** Propagate with A2A diagnostic context

## Observability

Executions produce metrics:
- `latency_ms` - Processing time
- `tokens` - Token usage (if applicable)
- `confidence` - Output confidence score
- `a2a_depth` - Call chain depth

### A2A-Specific Events
```jsonl
{"event":"a2a_context_received","correlation_id":"xyz-789","call_depth":2}
{"event":"skill_invoked","skill":"skill.your-domain-skill","correlation_id":"xyz-789"}
{"event":"a2a_result_packaged","correlation_id":"xyz-789","confidence":0.95}
```

## Testing

### Unit Test
```bash
uv run -m pytest tests/agents/test_your_a2a_advisor_sag.py -v
```

### Integration Test - Direct Invocation (via MAG)
```python
# SAGs are typically invoked by MAGs
delegation = Delegation(
    task_id="test-1",
    sag_id="your-a2a-advisor-sag",
    input={"domain_field": "test", "context": {...}},
    context={"parent_run_id": "mag-test"}
)
result = runner.invoke_sag(delegation)
assert result.status == "success"
```

### E2E Test
```bash
# Test as part of MAG orchestration
uv run -m pytest tests/integration/test_a2a_e2e.py -v
```

## Development Notes

### Customization Checklist
- [ ] Update agent.yaml with correct slug, name, and description
- [ ] Define input/output contracts in catalog/contracts/
- [ ] Implement domain logic in code/advisor.py
- [ ] Add A2A context handling
- [ ] Implement skill invocation with fallbacks
- [ ] Add comprehensive tests
- [ ] Document A2A capabilities
- [ ] Configure observability for A2A tracing

### A2A Best Practices
1. **Always preserve correlation_id** - Essential for end-to-end tracing
2. **Log call chain depth** - Helps detect circular dependencies
3. **Include processing time in trace** - Enables performance analysis
4. **Handle missing context gracefully** - Don't fail if context is incomplete
5. **Use structured logging** - Makes A2A flows easier to debug

### Future Enhancements
- Support for async processing
- Result caching based on correlation_id
- Automatic context validation
- A2A authentication support
- Circuit breaker integration
