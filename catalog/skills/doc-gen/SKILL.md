---
name: doc-gen
description: >
  Generates offer packet documents that summarize compensation recommendations and candidate-specific details.
iface:
  input_schema: catalog/contracts/candidate_profile.schema.json
  output_schema: catalog/contracts/offer_packet.schema.json
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
- The upstream orchestration workflow has collected a `candidate_profile` payload plus optional salary band guidance.
- A human or automated consumer needs a structured `offer_packet` JSON document that conforms to `catalog/contracts/offer_packet.schema.json`.
- The offer summary must stay consistent with `salary-band-lookup` guidance and advisor notes when present.

## Prerequisites
- Input payload must validate against `catalog/contracts/candidate_profile.schema.json`.
- Salary band recommendations and advisor notes are optional but improve the generated summary.
- MCP runtime is optional; when provided it will be used in future phases for remote data enrichment.

## Procedures

### Generate Offer Packet
1. **Validate Inputs** – Run schema validation on the incoming payload using `catalog/contracts/candidate_profile.schema.json`. Reject or request correction when required keys are missing.
2. **Collect Supporting Data** – Incorporate salary band guidance or advisor notes from the payload when present. If enrichment data is missing, surface a warning in the result.
3. **Compose Narrative Sections** – Draft role overview, compensation summary, and key talking points. Explicitly reference base salary, variable components, and any equity recommendations that are available.
4. **Assemble Structured Output** – Populate the JSON response so it satisfies `catalog/contracts/offer_packet.schema.json`, including metadata, narrative sections, and machine-readable compensation values.
5. **Quality Gate** – Perform a final schema validation before returning the payload. Include an audit trail of data sources in the `provenance` section when available.

## Examples

### Example 1: Minimal Candidate Record
- **Input**: [`resources/examples/in.json`](resources/examples/in.json)
- **Process**:
  1. Validate the stub candidate identifier.
 2. Merge salary band guidance if included in the payload.
 3. Draft the offer summary referencing available data.
- **Output**: [`resources/examples/out.json`](resources/examples/out.json)

## Additional Resources
- `resources/examples/` – Sample request and response objects.
- `impl/` – Placeholder directory for execution helpers or prompt templates.
- `catalog/contracts/offer_packet.schema.json` – Defines the expected structure for outgoing packets.

## Troubleshooting
- **Schema Validation Fails**: Confirm the caller transformed the upstream data with `catalog/contracts/candidate_profile.schema.json`; missing identifiers or compensation targets frequently cause this failure.
- **Missing Compensation Context**: When the payload lacks salary band guidance, emit a warning so the orchestrator can rerun `salary-band-lookup` before finalizing the packet.
- **Latency Spikes**: Execution is CPU-bound; unexpected latency often indicates heavy upstream preprocessing or oversized payloads.
