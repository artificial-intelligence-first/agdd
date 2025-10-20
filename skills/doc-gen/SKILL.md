---
name: doc-gen
description: >
  Generates offer packet documents that summarize compensation recommendations and candidate-specific details.
iface:
  input_schema: contracts/candidate_profile.json
  output_schema: contracts/offer_packet.json
mcp:
  server_ref: "pg-readonly"
slo:
  success_rate_min: 0.99
  latency_p95_ms: 1000
limits:
  rate_per_min: 60
---

## Purpose
Create a structured offer packet ready for delivery to candidates based on validated profile data and downstream advisor outputs.

## Procedure
1) Validate the incoming payload against `contracts/candidate_profile.json`.
2) Compose narrative and tabular offer sections using compensation guidance.
3) Validate the generated payload against `contracts/offer_packet.json` before returning it.

## Examples
- in:  resources/examples/in.json
- out: resources/examples/out.json

## Notes
- External network access is prohibited; use MCP resources only when additional data is required.
