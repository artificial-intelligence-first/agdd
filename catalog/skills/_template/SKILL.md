---
name: <skill-name>
description: >
  Summarize the capability provided by this skill and the inputs or situations that trigger it.
iface:
  input_schema: contracts/<in>.json
  output_schema: contracts/<out>.json
mcp:
  server_ref: "<server-id>"
slo:
  success_rate_min: 0.99
  latency_p95_ms: 1000
limits:
  rate_per_min: 60
---

# <Skill Display Name> (<skill-name>)

## Purpose
Explain the end-to-end outcome the skill produces and why it matters to the broader workflow.

## When to Use
- List clear trigger conditions and canonical user requests.
- Note complementary skills or orchestration steps that should run before or after this one.

## Prerequisites
- Describe required schemas, MCP connections, or cached context the skill expects.
- Call out configuration, policy constraints, or environment assumptions that must hold true.

## Procedures

### Procedure 1: <Action Name>
1. Provide step-by-step guidance starting with input validation.
2. Explain how to invoke supporting tools, databases, or prompts.
3. Include decision points or fallback behaviors the agent must apply.

### Procedure 2: <Optional Secondary Action>
1. Add additional flows when the skill supports multiple modes.
2. Reference how to select among the procedures based on input cues.

## Examples

### Example 1: <Scenario Name>
- **Input**: [resources/examples/in.json](resources/examples/in.json)
- **Process**:
  1. Summarize each major step taken.
  2. Mention external dependencies invoked.
- **Output**: [resources/examples/out.json](resources/examples/out.json)

Add additional scenarios to capture edge cases or advanced usage as needed.

## Additional Resources
- `resources/` – Point to sample payloads, prompts, or schemas.
- `impl/` – Document helper scripts or templates included with the skill package.
- Link to related policies or playbooks that influence decision making.

## Troubleshooting
- Describe common validation failures and how to resolve them.
- Highlight monitoring signals to check when SLOs degrade.
- Provide escalation contacts or follow-up actions when automation cannot recover.
