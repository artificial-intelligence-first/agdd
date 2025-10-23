# YourAdvisorSAG

**Role:** Sub-Agent (SAG)
**Version:** 0.1.0
**Status:** Template

## Overview

[Describe this SAG's specialized task and domain expertise]

## Responsibilities

- Execute domain-specific logic
- Return structured output conforming to contract
- Handle errors gracefully with meaningful messages

## Input Contract

**Schema:** `contracts/your_advisor_input.schema.json`

Example:
```json
{
  "domain_field": "value",
  "parameters": {
    "param1": 123
  }
}
```

## Output Contract

**Schema:** `contracts/your_advisor_output.schema.json`

Example:
```json
{
  "result": {
    "processed_field": "value"
  },
  "confidence": 0.95,
  "notes": "Optional explanatory text"
}
```

## Dependencies

### Skills
- `skill.your-domain-skill` - [Describe skill purpose]

## Execution Logic

1. **Input Validation** - Validate against input schema
2. **Domain Processing** - Apply specialized logic
3. **Skill Invocation** - Call required skills
4. **Output Formatting** - Package results per schema

## Error Handling

- **Invalid Input:** Return error with validation details
- **Skill Failure:** Log error and return partial/default result
- **Unexpected Exception:** Propagate with diagnostic context

## Observability

Executions produce metrics:
- `latency_ms` - Processing time
- `tokens` - Token usage (if applicable)
- `confidence` - Output confidence score

## Testing

```bash
# Unit test
uv run -m pytest tests/agents/test_your_advisor_sag.py -v

# Direct invocation
echo '{"domain_field":"test"}' > /tmp/input.json
# (SAGs are invoked by MAGs, not directly via CLI)
```

## Development Notes

[Add implementation notes, known limitations, future enhancements]
