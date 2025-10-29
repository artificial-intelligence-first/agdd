---
name: salary-band-lookup
description: >
  Provides recommended salary bands by combining internal compensation tables with candidate attributes.
iface:
  input_schema: catalog/contracts/candidate_profile.json
  output_schema: catalog/contracts/salary_band.json
mcp:
  server_ref: "pg-readonly"
slo:
  success_rate_min: 0.99
  latency_p95_ms: 1000
limits:
  rate_per_min: 60
---

# Salary Band Lookup (salary-band-lookup)

## Purpose
Compute salary band recommendations that align with internal compensation policy, using candidate attributes, job level expectations, and available market benchmarks.

## When to Use
- A candidate profile satisfying `catalog/contracts/candidate_profile.json` is available and the workflow requires salary guidance.
- Downstream skills or humans need normalized band information before generating offer packets or advisor summaries.
- The orchestrator must validate that proposed compensation falls within governance thresholds defined by policy.

## Prerequisites
- Established connection to the `pg-readonly` MCP server with access to compensation tables and market benchmark views.
- Candidate records must include role family, level, and geographic metadata for accurate lookup.
- Ensure the latest compensation policy tables are synchronized in the MCP data source.

## Procedures

### Retrieve and Calculate Salary Bands
1. **Validate Candidate Payload** – Confirm the input conforms to `catalog/contracts/candidate_profile.json`. Pay special attention to `role_family`, `level`, and `location` fields.
2. **Query Compensation Tables** – Execute deterministic reads via `pg-readonly` to fetch base, target, and stretch ranges for the specified job family and level. Incorporate location adjustments when available.
3. **Incorporate Market Benchmarks** – Blend internal tables with benchmark adjustments to produce a recommended range. Document the benchmark source in the response metadata.
4. **Apply Governance Rules** – Enforce policy thresholds (e.g., maximum variance vs. current employee compensation) and raise warnings if the recommended band conflicts with governance constraints.
5. **Emit Structured Output** – Populate fields defined in `catalog/contracts/salary_band.json`, including `recommended_band`, numeric ranges, currency codes, and rationale or caveats.
6. **Validate Results** – Run schema validation against `catalog/contracts/salary_band.json` to ensure completeness before returning the payload.

## Examples

### Example 1: Baseline Lookup
- **Input**: [`resources/examples/in.json`](resources/examples/in.json)
- **Process**:
  1. Validate `cand-123` against the candidate schema.
  2. Fetch level-specific bands via `pg-readonly`.
  3. Adjust for location differentials if present and compile reasoning.
- **Output**: [`resources/examples/out.json`](resources/examples/out.json)

## Additional Resources
- `resources/examples/` – Illustrative inputs and outputs for integration testing.
- `impl/` – Reserved directory for helper prompts, SQL, or scripts.
- `policies/flow_governance.yaml` – Reference governance thresholds when interpreting warnings (repository root).

## Troubleshooting
- **Missing Compensation Rows**: If `pg-readonly` returns zero results, return a warning and suggest verifying that the compensation tables contain the candidate's job family/level combination.
- **Schema Violations**: Ensure optional numeric ranges are emitted as numbers, not strings, and that currency codes follow ISO 4217.
- **Stale Benchmarks**: When benchmark metadata indicates an outdated refresh date, flag the issue in the `warnings` array and notify the compensation operations contact channel.
