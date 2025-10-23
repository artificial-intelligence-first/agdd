---
name: result-aggregation
description: >
  Aggregates results from multiple sub-agent executions into a unified output.
iface:
  input_schema: (list of result objects)
  output_schema: contracts/offer_packet.json
slo:
  success_rate_min: 0.99
  latency_p95_ms: 200
---

# Result Aggregation (result-aggregation)

## Purpose
Combines outputs from multiple sub-agent executions into a coherent final result.

## When to Use
- Multiple SAGs have completed their tasks
- MAG needs to synthesize outputs into final deliverable
- Results need normalization or conflict resolution

## Procedures
1. Validate each sub-agent result
2. Merge complementary data
3. Resolve conflicts using policy rules
4. Format output according to target schema

## Examples
Aggregating compensation data from compensation-advisor-sag into final offer packet.
