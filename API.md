# AGDD HTTP API Reference

The AG-Driven Development (AGDD) HTTP API provides remote access to the same agent orchestration workflows exposed by the CLI. This document supplements the interactive FastAPI docs (`/docs`, `/redoc`) with authentication guidance, request/response examples, and operational notes.

## Base URL and Versioning

- Default base URL: `http://localhost:8000`
- Prefix: `/api/v1`
- Health check: `GET /health`

The versioned prefix can be overridden with `AGDD_API_PREFIX`.

## Authentication

Authentication is disabled only when `AGDD_API_KEY` is unset (development mode). Production deployments must set a key and require it on every request using one of the following headers:

- `Authorization: Bearer <AGDD_API_KEY>`
- `x-api-key: <AGDD_API_KEY>`

Requests without a valid key return HTTP 401 with an `unauthorized` error payload.

## Rate Limiting

Configure `AGDD_RATE_LIMIT_QPS` to enable rate limiting.

- **In-memory token bucket** (default) – applies when `AGDD_RATE_LIMIT_QPS` is set and `AGDD_REDIS_URL` is unset.
- **Redis-backed limiter** – requires `AGDD_REDIS_URL` and shares limits across processes. Uses an atomic Lua script with unique timestamp+sequence members to avoid race conditions and timestamp collisions.

When the limit is exceeded, the API returns HTTP 429 with `{"code": "rate_limit_exceeded", "message": "..."}`. Redis outages fall back to a warning log and allow traffic (fail-open).

## Error Format

All error responses follow:

```json
{
  "code": "invalid_payload",
  "message": "Human readable description",
  "details": {"optional": "context"}
}
```

`code` values include `agent_not_found`, `invalid_payload`, `execution_failed`, `invalid_run_id`, `rate_limit_exceeded`, `unauthorized`, and `internal_error`.

## Endpoints

### `GET /api/v1/agents`

List registered agents from `registry/agents.yaml` and their descriptors.

```bash
curl -sS -H "Authorization: Bearer $AGDD_API_KEY" \
  http://localhost:8000/api/v1/agents | jq '.'
```

**Response**

```json
[
  {
    "slug": "offer-orchestrator-mag",
    "title": "Offer Orchestrator",
    "description": "Generate tailored offers"
  }
]
```

### `POST /api/v1/agents/{slug}/run`

Execute a MAG agent asynchronously. The request body must be an object with a `payload` key; optional `request_id` and `metadata` fields provide traceability.

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $AGDD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "payload": {
          "role": "Senior Engineer",
          "level": "Senior"
        },
        "request_id": "demo-001",
        "metadata": {"source": "api-doc"}
      }' \
  http://localhost:8000/api/v1/agents/offer-orchestrator-mag/run | jq '.'
```

**Successful response**

```json
{
  "run_id": "mag-20250101-abcdef",
  "slug": "offer-orchestrator-mag",
  "output": {"status": "success", "packet": {...}},
  "artifacts": {
    "summary": "/api/v1/runs/mag-20250101-abcdef",
    "logs": "/api/v1/runs/mag-20250101-abcdef/logs"
  }
}
```

Errors include:

- `404 agent_not_found` – slug not present in the registry
- `400 invalid_payload` – payload fails schema validation
- `400 execution_failed` – runtime error surfaced from the agent implementation
- `500 internal_error` – unexpected failure (see logs)

### `GET /api/v1/runs/{run_id}`

Retrieve run metadata, summary, metrics, and a flag indicating if logs exist.

```bash
curl -sS -H "Authorization: Bearer $AGDD_API_KEY" \
  http://localhost:8000/api/v1/runs/mag-20250101-abcdef | jq '.'
```

**Response**

```json
{
  "run_id": "mag-20250101-abcdef",
  "slug": "offer-orchestrator-mag",
  "summary": {"status": "success"},
  "metrics": {"latency_ms": 18234},
  "has_logs": true
}
```

### `GET /api/v1/runs/{run_id}/logs`

Stream log lines from `.runs/agents/<RUN_ID>/logs.jsonl`.

- `tail` (int, optional) – return only the last N lines
- `follow` (bool, optional) – enable Server-Sent Events streaming

```bash
# Retrieve the last 20 lines
curl -sS -H "Authorization: Bearer $AGDD_API_KEY" \
  "http://localhost:8000/api/v1/runs/mag-20250101-abcdef/logs?tail=20"

# Follow in real time (SSE)
curl -N -H "Authorization: Bearer $AGDD_API_KEY" \
  "http://localhost:8000/api/v1/runs/mag-20250101-abcdef/logs?follow=true&tail=5"
```

When `follow=true`, the response uses `text/event-stream` with `data:` lines suitable for EventSource clients. Without `follow`, the response is NDJSON (`application/x-ndjson`).

### `POST /api/v1/github/webhook`

Receive GitHub events. Requests must supply the `X-Hub-Signature-256` header when `AGDD_GITHUB_WEBHOOK_SECRET` is set. The handler processes:

- `issue_comment`
- `pull_request_review_comment`
- `pull_request`

Unsupported events return `{"status": "ok"}` to avoid retries. See [GITHUB.md](./GITHUB.md) for complete flow details.

### `GET /api/v1/github/health`

Lightweight health probe for GitHub webhook deployments.

```bash
curl -sS http://localhost:8000/api/v1/github/health | jq '.'
```

## Run Tracking and Observability

- Runs are stored under `.runs/agents/<RUN_ID>`.
- `summary.json`, `metrics.json`, and `logs.jsonl` are exposed via the API.
- `run_id` is auto-detected by comparing directory snapshots before/after agent execution and inspecting `summary.json`.
- Responses include `artifacts` URLs that map directly to API endpoints for easy retrieval.

## Additional Resources

- [`examples/api/curl_examples.sh`](./examples/api/curl_examples.sh) – end-to-end curl walkthrough with commentary.
- [`scripts/run-api-server.sh`](./scripts/run-api-server.sh) – helper for launching the FastAPI service.
- [`GITHUB.md`](./GITHUB.md) – GitHub integration workflows.

For endpoint-specific examples, consult the FastAPI interactive docs or the integration tests under `tests/integration/`.
