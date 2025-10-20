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

## Purpose
## Procedure
1) Validate the input against the declared schema -> 2) Execute the core logic -> 3) Validate the output schema
## Examples
- in:  resources/examples/in.json
- out: resources/examples/out.json
## Notes
- External network access is forbidden; only MCP-mediated connectivity is permitted.
