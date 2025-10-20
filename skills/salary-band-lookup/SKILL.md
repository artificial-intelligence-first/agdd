---
name: salary-band-lookup
description: >
  Provides recommended salary bands by combining internal compensation tables with candidate attributes.
iface:
  input_schema: contracts/candidate_profile.json
  output_schema: contracts/salary_band.json
mcp:
  server_ref: "pg-readonly"
slo:
  success_rate_min: 0.99
  latency_p95_ms: 1000
limits:
  rate_per_min: 60
---

## Purpose
Advise downstream agents on competitive salary ranges aligned with internal compensation policy and market insights.

## Procedure
1) Validate the candidate payload against `contracts/candidate_profile.json`.
2) Query compensation data via the `pg-readonly` MCP server and compute recommendation bands.
3) Validate and emit structured salary guidance using `contracts/salary_band.json`.

## Examples
- in:  resources/examples/in.json
- out: resources/examples/out.json

## Notes
- External network access is prohibited; compensation data must flow through MCP-managed connections.
