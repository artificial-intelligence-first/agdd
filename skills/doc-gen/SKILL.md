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

# Doc Generation (doc-gen)

## Purpose
Produce a complete offer packet that combines validated candidate data, compensation recommendations, and narrative guidance that can be delivered directly to the recruiting partner or hiring manager.

## When to Use
- The upstream orchestration workflow has collected a `candidate_profile` payload and downstream salary band data.
- A human or automated consumer needs a structured `offer_packet` JSON document that conforms to `contracts/offer_packet.json`.
- The offer summary must be consistent with guidance produced by the `salary-band-lookup` skill and any advisor notes.

## Prerequisites
- Input payload must validate against `contracts/candidate_profile.json`.
- Access to the `pg-readonly` MCP server for compensation enrichment queries.
- Availability of salary band recommendations or advisor notes in the candidate context (if absent, call out missing inputs in the output).

## Procedures

### Generate Offer Packet
1. **Validate Inputs** – Run schema validation on the incoming payload using `contracts/candidate_profile.json`. Reject or request correction when required keys are missing.
2. **Collect Supporting Data** – Pull market benchmarks and previously generated salary band guidance through the `pg-readonly` server. If the data is unavailable, log a warning in the `warnings` field of the result.
3. **Compose Narrative Sections** – Draft role overview, compensation summary, and key talking points. Explicitly reference base salary, variable components, and any equity recommendations.
4. **Assemble Structured Output** – Populate the JSON response so it satisfies `contracts/offer_packet.json`, including metadata, narrative sections, and machine-readable compensation values.
5. **Quality Gate** – Perform a final schema validation against `contracts/offer_packet.json` before returning the payload. Include an audit trail of data sources in the `provenance` or `notes` sections when available.

## Examples

### Example 1: Minimal Candidate Record
- **Input**: [`resources/examples/in.json`](resources/examples/in.json)
- **Process**:
  1. Validate the stub candidate identifier.
  2. Retrieve compensation history for `cand-123` via `pg-readonly`.
  3. Draft offer summary referencing the retrieved bands.
- **Output**: [`resources/examples/out.json`](resources/examples/out.json)

## Additional Resources
- `resources/examples/` – Sample request and response objects.
- `impl/` – Placeholder directory for execution helpers or prompt templates.
- `contracts/offer_packet.json` – Defines the expected structure for outgoing packets (located at repository root).

## Troubleshooting
- **Schema Validation Fails**: Confirm the caller transformed the upstream data with `contracts/candidate_profile.json`; missing identifiers or compensation targets frequently cause this failure.
- **Missing Compensation Context**: If `pg-readonly` returns no rows, insert a `warnings` entry describing the gap and advise rerunning `salary-band-lookup`.
- **Latency Spikes**: Inspect MCP query complexity and ensure the rate limits specified above are respected to remain within the 1000 ms p95 target.
