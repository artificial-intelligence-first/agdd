# AGDD HTTP API Reference

The AG-Driven Development (AGDD) HTTP API exposes agent orchestration, run observability, and GitHub automation over FastAPI. This document provides an end-to-end reference for configuration, authentication, endpoints, and troubleshooting.

## Base URL and Configuration

| Setting | Description | Default |
| --- | --- | --- |
| `AGDD_API_HOST` | Host interface for uvicorn | `0.0.0.0` |
| `AGDD_API_PORT` | Listening port | `8000` |
| `AGDD_API_PREFIX` | URL prefix for versioned endpoints | `/api/v1` |
| `AGDD_API_DEBUG` | Enables FastAPI debug and auto-reload (dev only) | `false` |
| `AGDD_RUNS_BASE_DIR` | Filesystem root for agent run artifacts | `.runs/agents` |
| `AGDD_API_KEY` | Shared secret for bearer/x-api-key authentication | `None` (disabled) |
| `AGDD_RATE_LIMIT_QPS` | Requests per second per credential/IP | `None` (disabled) |
| `AGDD_REDIS_URL` | Redis connection string for distributed rate limiting | `None` |
| `AGDD_GITHUB_WEBHOOK_SECRET` | Secret for GitHub HMAC verification | `None` |
| `AGDD_GITHUB_TOKEN` | Token used for posting GitHub comments | `None` |

Run artifacts default to `.runs/agents`, and cost ledgers are persisted separately under `.runs/costs/` via `agdd.observability.cost_tracker`.

Create a `.env` file (see `.env.example`) to override these defaults before launching `uvicorn`:

```bash
cp .env.example .env
uv run uvicorn agdd.api.server:app --host 0.0.0.0 --port 8000
```

## Authentication

- **API Key (recommended):** Configure `AGDD_API_KEY` and supply either an `Authorization: Bearer <token>` header or `x-api-key: <token>` with each request.
- **Unauthenticated development:** Leave `AGDD_API_KEY` unset. Authentication is skipped, but the rate limiter still keys on client IP.
- **GitHub webhook:** Set `AGDD_GITHUB_WEBHOOK_SECRET`. Incoming webhook signatures are verified via `X-Hub-Signature-256` using HMAC SHA-256. Requests without a valid signature receive HTTP 401.

Secrets are intentionally never echoed in logs, example scripts, or error messages.

## Rate Limiting

Set `AGDD_RATE_LIMIT_QPS` to enable a token-bucket limiter. By default it uses an in-memory store (process-wide). Provide `AGDD_REDIS_URL` for multi-process deployments; a Lua script ensures atomic updates and tags each request with a unique `timestamp:seq` member to avoid race conditions.

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

Configure `AGDD_API_MAX_REQUEST_BYTES` (default: 10 MiB) to reject oversized payloads early. Requests exceeding the limit respond with HTTP 413 and `{"detail": "Request body too large"}`; malformed `Content-Length` headers return HTTP 400. Adjust the limit to match your expected request sizes.

## Endpoints

All routes below are prefixed with `AGDD_API_PREFIX` (`/api/v1` by default) unless otherwise noted.

### `GET /agents`

Lists registered agents from `registry/agents.yaml`.

- **Authentication:** Required when `AGDD_API_KEY` is set
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

- **Authentication:** Required when `AGDD_API_KEY` is set
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
  "run_id": "mag-20240101-abcdef",
  "slug": "offer-orchestrator-mag",
  "output": {"offer": {"role": "Senior Engineer"}},
  "artifacts": {
    "summary": "/api/v1/runs/mag-20240101-abcdef",
    "logs": "/api/v1/runs/mag-20240101-abcdef/logs"
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

- **Authentication:** Required when `AGDD_API_KEY` is set
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

- **Authentication:** Required when `AGDD_API_KEY` is set
- **Query Parameters:**
  - `tail` (int): Return only the last N lines
  - `follow` (bool): When true, respond with `text/event-stream` and keep streaming new log lines (Server-Sent Events)

When `follow=false`, the response media type is `application/x-ndjson`.

### `POST /github/webhook`

Processes GitHub events:

- `issue_comment`
- `pull_request_review_comment`
- `pull_request`

Commands of the form ``@agent-slug {"key": "value"}`` trigger agent execution. Results (success or failure) are posted back to GitHub using `AGDD_GITHUB_TOKEN`.

- **Authentication:** Signature verification via `AGDD_GITHUB_WEBHOOK_SECRET`
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
export AGDD_API_KEY="local-dev-key"

# List agents
curl -sS -H "Authorization: Bearer $AGDD_API_KEY" \
  "$API_URL/api/v1/agents" | jq

# Run an agent
curl -sS -X POST \
  -H "Authorization: Bearer $AGDD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"payload": {"role": "Staff Engineer", "experience_years": 12}}' \
  "$API_URL/api/v1/agents/offer-orchestrator-mag/run"

# Tail logs
RUN_ID="mag-20240101-abcdef"
curl -sS -H "Authorization: Bearer $AGDD_API_KEY" \
  "$API_URL/api/v1/runs/$RUN_ID/logs?tail=20"

# Follow logs with SSE (Ctrl+C to exit)
curl -N -H "Authorization: Bearer $AGDD_API_KEY" \
  "$API_URL/api/v1/runs/$RUN_ID/logs?follow=true"
```

The `examples/api/curl_examples.sh` script provides a guided tour of every endpoint, including error handling scenarios.

## Run Tracking and Observability

- Run directories are created under `.runs/agents/`.
- `summary.json` and `metrics.json` are parsed to populate the `/runs/{run_id}` response.
- `logs.jsonl` is streamed directly for `/runs/{run_id}/logs`.
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

- **`401 Unauthorized`:** Ensure the request includes the correct API key or disable auth locally by removing `AGDD_API_KEY`.
- **`401 invalid_signature`:** Confirm the webhook secret matches the value configured in GitHub and the API server.
- **`429 Too Many Requests`:** Increase `AGDD_RATE_LIMIT_QPS`, deploy Redis for horizontal scaling, or stagger automation jobs.
- **`404 Run not found`:** The MAG may still be running. Poll `/runs/{run_id}` and confirm run artifacts under `.runs/agents/`.
- **SSE drops:** Some proxies buffer Server-Sent Events. Use `tail` polling as a fallback when streaming is not supported.

For GitHub-specific diagnostics, refer to [GitHub Integration Guide](./github-integration.md).
