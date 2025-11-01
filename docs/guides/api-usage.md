---
title: MAGSAG HTTP API Reference
last_synced: 2025-10-25
description: Complete reference for MAGSAG FastAPI endpoints, authentication, and observability
change_log:
  - 2025-10-25: Phase 3 - Fixed authentication error response format to match documented schema
  - 2025-10-25: Phase 3 - Updated run ID examples to use correct format (mag-{8-char-hex})
  - 2025-10-24: Added front-matter and SSE/NDJSON contract specifications
  - 2025-10-24: Added run_id format specification and retrieval documentation
---

# MAGSAG HTTP API Reference

The MAGSAG HTTP API exposes agent orchestration, run observability, and GitHub automation over FastAPI. This document provides an end-to-end reference for configuration, authentication, endpoints, and troubleshooting.

## Base URL and Configuration

| Setting | Description | Default |
| --- | --- | --- |
| `MAGSAG_API_HOST` | Host interface for uvicorn | `0.0.0.0` |
| `MAGSAG_API_PORT` | Listening port | `8000` |
| `MAGSAG_API_PREFIX` | URL prefix for versioned endpoints | `/api/v1` |
| `MAGSAG_API_DEBUG` | Enables FastAPI debug and auto-reload (dev only) | `false` |
| `MAGSAG_RUNS_BASE_DIR` | Filesystem root for agent run artifacts | `.runs/agents` |
| `MAGSAG_API_KEY` | Shared secret for bearer/x-api-key authentication | `None` (disabled) |
| `MAGSAG_RATE_LIMIT_QPS` | Requests per second per credential/IP | `None` (disabled) |
| `MAGSAG_REDIS_URL` | Redis connection string for distributed rate limiting | `None` |
| `MAGSAG_GITHUB_WEBHOOK_SECRET` | Secret for GitHub HMAC verification | `None` |
| `MAGSAG_GITHUB_TOKEN` | Token used for posting GitHub comments | `None` |

Run artifacts default to `.runs/agents`, and cost ledgers are persisted separately under `.runs/costs/` via `magsag.observability.cost_tracker`.

Create a `.env` file (see `.env.example`) to override these defaults before launching `uvicorn`:

```bash
cp .env.example .env
uv run uvicorn magsag.api.server:app --host 0.0.0.0 --port 8000
```

## Authentication

- **API Key (recommended):** Configure `MAGSAG_API_KEY` and supply either an `Authorization: Bearer <token>` header or `x-api-key: <token>` with each request.
- **Unauthenticated development:** Leave `MAGSAG_API_KEY` unset. Authentication is skipped, but the rate limiter still keys on client IP.
- **GitHub webhook:** Set `MAGSAG_GITHUB_WEBHOOK_SECRET`. Incoming webhook signatures are verified via `X-Hub-Signature-256` using HMAC SHA-256. Requests without a valid signature receive HTTP 401.

Secrets are intentionally never echoed in logs, example scripts, or error messages.

## Rate Limiting

Set `MAGSAG_RATE_LIMIT_QPS` to enable a token-bucket limiter. By default it uses an in-memory store (process-wide). Provide `MAGSAG_REDIS_URL` for multi-process deployments; a Lua script ensures atomic updates and tags each request with a unique `timestamp:seq` member to avoid race conditions.

Rate limits are keyed by:

1. `x-api-key` header (if present)
2. Bearer token from the `Authorization` header
3. Client IP address as a fallback

Exceeding the limit returns HTTP 429 with:

```json
{
  "code": "rate_limit_exceeded",
  "message": "Rate limit exceeded. Maximum <QPS> requests per second."
}
```

## Request Size Limits

Configure `MAGSAG_API_MAX_REQUEST_BYTES` (default: 10 MiB) to reject oversized payloads early. Requests exceeding the limit respond with HTTP 413 and `{"detail": "Request body too large"}`; malformed `Content-Length` headers return HTTP 400. Adjust the limit to match your expected request sizes.

## Endpoints

All routes below are prefixed with `MAGSAG_API_PREFIX` (`/api/v1` by default) unless otherwise noted.

### `GET /agents`

Lists registered agents from `registry/agents.yaml`.

- **Authentication:** Required when `MAGSAG_API_KEY` is set
- **Query Parameters:** None
- **Response (200):**

```json
[
  {
    "slug": "offer-orchestrator-mag",
    "title": "OfferOrchestratorMAG",
    "description": "Generates tailored compensation offers."
  }
]
```

### `POST /agents/{slug}/run`

Executes a main agent (MAG) and returns its output plus run metadata.

- **Authentication:** Required when `MAGSAG_API_KEY` is set
- **Body:**

```json
{
  "payload": {"role": "Senior Engineer"},
  "request_id": "optional-client-id",
  "metadata": {"source": "ci"}
}
```

- **Response (200):**

```json
{
  "run_id": "mag-a1b2c3d4",
  "slug": "offer-orchestrator-mag",
  "output": {"offer": {"role": "Senior Engineer"}},
  "artifacts": {
    "summary": "/api/v1/runs/mag-a1b2c3d4",
    "logs": "/api/v1/runs/mag-a1b2c3d4/logs"
  }
}
```

- **Errors:**
  - `404 agent_not_found` – unknown slug or missing agent descriptor
  - `400 invalid_payload` – schema mismatch or validation failure
  - `400 execution_failed` – runtime error surfaced from the MAG/SAG pipeline
  - `500 internal_error` – unexpected exceptions

### `GET /runs/{run_id}`

Retrieves summary (`summary.json`) and metrics (`metrics.json`) for a completed run. The run ID is validated to prevent directory traversal.

- **Authentication:** Required when `MAGSAG_API_KEY` is set
- **Response (200):**

```json
{
  "run_id": "mag-20240101-abcdef",
  "slug": "offer-orchestrator-mag",
  "summary": {"status": "success"},
  "metrics": {"latency_ms": 845},
  "has_logs": true
}
```

- **Errors:**
  - `400 invalid_run_id` – illegal characters or traversal attempt
  - `404 not_found` – no metrics, summary, or logs available for the ID

### `GET /runs/{run_id}/logs`

Streams newline-delimited logs.

- **Authentication:** Required when `MAGSAG_API_KEY` is set
- **Query Parameters:**
  - `tail` (int): Return only the last N lines
  - `follow` (bool): When true, respond with `text/event-stream` and keep streaming new log lines (Server-Sent Events)

#### Response Formats

**NDJSON Mode** (`follow=false`, Content-Type: `application/x-ndjson`):
- Each line is a complete JSON object followed by `\n`
- Streams entire file or last N lines if `tail` specified
- Connection closes after all data sent
- Example:
  ```ndjson
  {"run_id":"mag-a1b2c3d4","event":"start","timestamp":1698765432.1,"data":{},"span_id":"span-abc"}
  {"run_id":"mag-a1b2c3d4","event":"delegation","timestamp":1698765432.5,"data":{"sag":"advisor"},"span_id":"span-def","parent_span_id":"span-abc"}
  ```

**SSE Mode** (`follow=true`, Content-Type: `text/event-stream`):
- Server-Sent Events format: `data: {json}\n\n`
- Optionally sends last N lines first if `tail` specified
- Polls for new log entries every 500ms
- Connection remains open for real-time streaming
- Client should handle reconnection on disconnect
- Example:
  ```
  data: {"run_id":"mag-a1b2c3d4","event":"start","timestamp":1698765432.1,"data":{},"span_id":"span-abc"}

  data: {"run_id":"mag-a1b2c3d4","event":"progress","timestamp":1698765433.2,"data":{"step":1},"span_id":"span-abc"}

  ```

#### Log Entry Schema

Each log entry is a JSON object with the following fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `run_id` | string | Yes | Unique run identifier |
| `event` | string | Yes | Event type (e.g., `start`, `delegation`, `finish`, `error`) |
| `timestamp` | float | Yes | Unix timestamp (seconds since epoch) |
| `data` | object | Yes | Event-specific payload |
| `span_id` | string | Yes | OpenTelemetry span identifier |
| `parent_span_id` | string | No | Parent span ID for nested operations |

Common event types:
- `start` - Execution started
- `delegation` - Task delegated to SAG
- `tool_call` - External tool invoked
- `finish` - Execution completed
- `error` - Error occurred

#### Backward Compatibility

The log entry schema is considered **stable**. Changes follow semantic versioning:
- **Adding optional fields**: Minor version bump
- **Removing or renaming fields**: Major version bump
- **Changing field types**: Major version bump

Clients should ignore unknown fields for forward compatibility.

### `POST /github/webhook`

Processes GitHub events:

- `issue_comment`
- `pull_request_review_comment`
- `pull_request`

Commands of the form ``@agent-slug {"key": "value"}`` trigger agent execution. Results (success or failure) are posted back to GitHub using `MAGSAG_GITHUB_TOKEN`.

- **Authentication:** Signature verification via `MAGSAG_GITHUB_WEBHOOK_SECRET`
- **Rate Limiting:** Enabled via dependency injection
- **Response (200):** `{ "status": "ok" }`

### `GET /github/health`

Lightweight health probe for GitHub integration consumers.

### `GET /health`

Root-level health check primarily used by load balancers and uptime monitors. No authentication is enforced.

## Curl Examples

```bash
# Export once
export API_URL="http://localhost:8000"
export MAGSAG_API_KEY="local-dev-key"

# List agents
curl -sS -H "Authorization: Bearer $MAGSAG_API_KEY" \
  "$API_URL/api/v1/agents" | jq

# Run an agent
curl -sS -X POST \
  -H "Authorization: Bearer $MAGSAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"payload": {"role": "Staff Engineer", "experience_years": 12}}' \
  "$API_URL/api/v1/agents/offer-orchestrator-mag/run"

# Tail logs
RUN_ID="mag-a1b2c3d4"
curl -sS -H "Authorization: Bearer $MAGSAG_API_KEY" \
  "$API_URL/api/v1/runs/$RUN_ID/logs?tail=20"

# Follow logs with SSE (Ctrl+C to exit)
curl -N -H "Authorization: Bearer $MAGSAG_API_KEY" \
  "$API_URL/api/v1/runs/$RUN_ID/logs?follow=true"
```

The `examples/api/curl_examples.sh` script provides a guided tour of every endpoint, including error handling scenarios.

## Run Tracking and Observability

### Run ID Format

Every agent execution is assigned a unique `run_id` that identifies the run and its artifacts:

- **Main Agent (MAG)**: `mag-{8-char-hex}`
  - Example: `mag-a1b2c3d4`
- **Sub-Agent (SAG)**: `sag-{8-char-hex}`
  - Example: `sag-e5f6a7b8`

The hex suffix is generated from a UUID v4 (8 characters = first 8 hex digits of UUID).

### Run ID Retrieval

When executing an agent via `POST /agents/{slug}/run`, the API response always includes the `run_id`:

```json
{
  "run_id": "mag-a1b2c3d4",
  "slug": "offer-orchestrator-mag",
  "output": {...},
  "artifacts": {
    "summary": "/api/v1/runs/mag-a1b2c3d4",
    "logs": "/api/v1/runs/mag-a1b2c3d4/logs"
  }
}
```

Clients should use the returned `run_id` to retrieve run artifacts and logs. Do not attempt to construct run IDs manually.

### Directory Structure

Run artifacts are stored in the following structure:

```
.runs/agents/{run_id}/
├── summary.json    # Run metadata, status, and metrics summary
├── metrics.json    # Detailed time-series metrics
└── logs.jsonl      # Newline-delimited JSON log entries
```

### API Endpoints

- `summary.json` and `metrics.json` are parsed to populate the `GET /runs/{run_id}` response.
- `logs.jsonl` is streamed directly for `GET /runs/{run_id}/logs`.
- The run tracker validates run IDs to guard against path traversal attacks and inspects the filesystem to determine newly created run folders.

## Error Reference

Common error payloads:

| HTTP | `code` | Description |
| --- | --- | --- |
| 400 | `invalid_payload` | Request body failed validation |
| 400 | `invalid_run_id` | Run identifier failed security checks |
| 401 | `unauthorized` | Missing or incorrect API key |
| 401 | `invalid_signature` | GitHub webhook signature mismatch |
| 404 | `agent_not_found` | Unknown agent slug |
| 404 | `not_found` | Missing run artifacts or logs |
| 429 | `rate_limit_exceeded` | QPS limit exceeded |
| 500 | `internal_error` | Unexpected server-side failure |

## Troubleshooting

- **`401 Unauthorized`:** Ensure the request includes the correct API key or disable auth locally by removing `MAGSAG_API_KEY`.
- **`401 invalid_signature`:** Confirm the webhook secret matches the value configured in GitHub and the API server.
- **`429 Too Many Requests`:** Increase `MAGSAG_RATE_LIMIT_QPS`, deploy Redis for horizontal scaling, or stagger automation jobs.
- **`404 Run not found`:** The MAG may still be running. Poll `/runs/{run_id}` and confirm run artifacts under `.runs/agents/`.
- **SSE drops:** Some proxies buffer Server-Sent Events. Use `tail` polling as a fallback when streaming is not supported.

For GitHub-specific diagnostics, refer to [GitHub Integration Guide](./github-integration.md).
