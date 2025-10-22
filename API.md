# AGDD HTTP API Reference

This document describes the production-ready FastAPI surface that powers AG-Driven Development (AGDD).
Use it alongside the interactive docs (`/docs`, `/redoc`) when integrating external systems.

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [Rate Limiting](#rate-limiting)
- [Environment Configuration](#environment-configuration)
- [Endpoints](#endpoints)
  - [GET /health](#get-health)
  - [GET /api/v1/agents](#get-apiv1agents)
  - [POST /api/v1/agents/{slug}/run](#post-apiv1agentsslugrun)
  - [GET /api/v1/runs/{run_id}](#get-apiv1runsrun_id)
  - [GET /api/v1/runs/{run_id}/logs](#get-apiv1runsrun_idlogs)
  - [POST /api/v1/github/webhook](#post-apiv1githubwebhook)
  - [GET /api/v1/github/health](#get-apiv1githubhealth)
- [Run Tracking and Observability](#run-tracking-and-observability)
- [Error Codes](#error-codes)
- [Troubleshooting](#troubleshooting)

## Overview

- RESTful endpoints for discovering agents, triggering executions, and retrieving observability artifacts
- Server-Sent Events (SSE) for real-time log streaming
- API key authentication and GitHub webhook signature validation
- Optional Redis-backed rate limiting for multi-process deployments
- Thread-pooled execution that reuses the existing CLI runtime (`invoke_mag`)

The canonical list of curl recipes lives in [`examples/api/curl_examples.sh`](./examples/api/curl_examples.sh).

## Authentication

Authentication is disabled when `AGDD_API_KEY` is unset (development mode).
Set a strong API key in production and present it via one of the following headers:

| Header | Example |
| ------ | ------- |
| `Authorization` | `Authorization: Bearer $AGDD_API_KEY` |
| `x-api-key` | `x-api-key: $AGDD_API_KEY` |

If both headers are present the bearer token takes precedence.

## Rate Limiting

Configure rate limiting with the following settings:

- `AGDD_RATE_LIMIT_QPS`: Enable rate limiting and set the per-client queries-per-second budget.
- `AGDD_REDIS_URL`: Optional. When provided the API uses Redis for distributed, atomic enforcement via a Lua script.
- `AGDD_CORS_ORIGINS`: Ensure cross-origin requests are restricted before enabling credentials support.

Redis deployments require the `redis` package. Install it with `uv pip install redis` or add the
`redis` optional dependency defined in `pyproject.toml` (`uv sync --extra redis`).

## Environment Configuration

Copy `.env.example` to `.env` and set the values listed below:

| Variable | Description |
| -------- | ----------- |
| `AGDD_API_DEBUG` | Enables FastAPI debug mode and autoreload |
| `AGDD_API_PREFIX` | Prefix for all API routes (default `/api/v1`) |
| `AGDD_API_HOST` / `AGDD_API_PORT` | Bind address and port for Uvicorn |
| `AGDD_API_KEY` | Bearer token required for client access |
| `AGDD_CORS_ORIGINS` | JSON array of allowed origins |
| `AGDD_CORS_ALLOW_CREDENTIALS` | Whether cookies/authorization headers may be sent |
| `AGDD_RUNS_BASE_DIR` | Directory containing observability artifacts |
| `AGDD_RATE_LIMIT_QPS` | Requests per second per client |
| `AGDD_REDIS_URL` | Redis connection URI for distributed rate limiting |
| `AGDD_GITHUB_WEBHOOK_SECRET` | Shared secret for verifying GitHub HMAC signatures |
| `AGDD_GITHUB_TOKEN` | Token used to post success/error comments back to GitHub |

## Endpoints

All endpoints are rooted at the configured `AGDD_API_PREFIX` (default `/api/v1`) unless otherwise noted.
Sample responses show success payloads. Errors conform to the [error schema](#error-codes).

### GET /health

Lightweight readiness probe for load balancers and orchestrators.

```bash
curl -H "Authorization: Bearer $AGDD_API_KEY" http://localhost:8000/health
```

Response:

```json
{"status": "ok"}
```

### GET /api/v1/agents

List registered agents using the canonical registry (`registry/agents.yaml`).

```bash
curl -H "Authorization: Bearer $AGDD_API_KEY" \
     http://localhost:8000/api/v1/agents | jq
```

Response snippet:

```json
[
  {
    "slug": "offer-orchestrator-mag",
    "title": "Offer Orchestrator",
    "description": "Coordinates compensation and offer packet creation"
  }
]
```

### POST /api/v1/agents/{slug}/run

Execute a MAG agent with the provided payload. Execution happens in a thread pool to avoid blocking the event loop.

```bash
curl -H "Authorization: Bearer $AGDD_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
           "payload": {
             "role": "Senior Engineer",
             "level": "Senior"
           },
           "request_id": "demo-$(date +%s)",
           "metadata": {
             "source": "api-doc-example"
           }
         }' \
     http://localhost:8000/api/v1/agents/offer-orchestrator-mag/run | jq
```

Successful response:

```json
{
  "run_id": "mag-20250101-abcdef",
  "slug": "offer-orchestrator-mag",
  "output": {
    "result": "... agent output ..."
  },
  "artifacts": {
    "summary": "/api/v1/runs/mag-20250101-abcdef",
    "logs": "/api/v1/runs/mag-20250101-abcdef/logs"
  }
}
```

### GET /api/v1/runs/{run_id}

Fetch summary and metrics artifacts generated by the ObservabilityLogger.

```bash
curl -H "Authorization: Bearer $AGDD_API_KEY" \
     http://localhost:8000/api/v1/runs/mag-20250101-abcdef | jq
```

Response:

```json
{
  "run_id": "mag-20250101-abcdef",
  "slug": "offer-orchestrator-mag",
  "summary": {"status": "success"},
  "metrics": {"latency_ms": 1234},
  "has_logs": true
}
```

### GET /api/v1/runs/{run_id}/logs

Return structured logs as newline-delimited JSON. The `tail` query parameter limits the output, and `follow=true`
upgrades the response to Server-Sent Events for live streaming.

```bash
# Last 20 lines
curl -H "Authorization: Bearer $AGDD_API_KEY" \
     "http://localhost:8000/api/v1/runs/mag-20250101-abcdef/logs?tail=20"

# Live stream via SSE
curl -N -H "Authorization: Bearer $AGDD_API_KEY" \
     "http://localhost:8000/api/v1/runs/mag-20250101-abcdef/logs?follow=true"
```

When `follow=true` each log line is emitted as an SSE `data:` event, making it compatible with `curl -N`, browsers, or EventSource clients.

### POST /api/v1/github/webhook

Receive GitHub webhooks and trigger agent executions when comments contain `@agent-slug {json}` commands.

Headers:

- `X-GitHub-Event`: GitHub event type (issue_comment, pull_request_review_comment, pull_request)
- `X-Hub-Signature-256`: HMAC signature (`sha256=` prefix) signed with `AGDD_GITHUB_WEBHOOK_SECRET`

Example using a recorded payload (replace `<signature>` with the HMAC SHA-256 digest of the request body using `AGDD_GITHUB_WEBHOOK_SECRET`):

```bash
curl -X POST \
     -H "Content-Type: application/json" \
     -H "X-GitHub-Event: issue_comment" \
     -H "X-Hub-Signature-256: sha256=<signature>" \
     --data @payload.json \
     http://localhost:8000/api/v1/github/webhook
```

Successful response:

```json
{"status": "ok"}
```

### GET /api/v1/github/health

Lightweight health check dedicated to the GitHub integration.

```bash
curl http://localhost:8000/api/v1/github/health
```

Response:

```json
{"status": "healthy", "integration": "github"}
```

## Run Tracking and Observability

- Run directories live under `AGDD_RUNS_BASE_DIR` (default `.runs/agents`).
- `find_new_run_id` detects new run IDs by comparing filesystem snapshots before and after execution.
- Summaries (`summary.json`), metrics (`metrics.json`), and logs (`logs.jsonl`) are exposed via the `/runs` endpoints.
- SSE log streaming is implemented with `aiofiles` and FastAPI `StreamingResponse` to support both polling and live tailing.

## Error Codes

Errors conform to the `ApiError` schema with the following `code` values:

| Code | Meaning |
| ---- | ------- |
| `agent_not_found` | Requested agent slug is missing |
| `invalid_payload` | Request body failed validation |
| `execution_failed` | Agent raised a recoverable runtime error |
| `invalid_run_id` | Run identifier failed security validation |
| `not_found` | Run artifacts were not located |
| `unauthorized` | API key missing or incorrect |
| `rate_limit_exceeded` | Rate limiter rejected the request |
| `invalid_signature` | GitHub webhook signature verification failed |
| `internal_error` | Unexpected server-side failure |

Each response includes a human-readable `message` and optional `details` object.

## Troubleshooting

- **CORS errors**: Ensure `AGDD_CORS_ORIGINS` contains explicit origins when enabling credentials.
- **Missing run IDs**: Agents may omit `run_id` from their output; the API falls back to filesystem detection within two seconds of completion.
- **GitHub comment not posting**: Confirm `AGDD_GITHUB_TOKEN` grants `repo` scope and the webhook event is one of the supported types.
- **Redis unavailable**: The rate limiter fails open but logs warnings; monitor application logs for `Redis rate limiter failure` messages.

For further guidance consult [GITHUB.md](./GITHUB.md) and the examples under [`examples/api/`](./examples/api/).
