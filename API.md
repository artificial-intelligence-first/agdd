# AGDD HTTP API Reference

The AG-Driven Development (AGDD) HTTP API exposes agent orchestration,
observability, and GitHub automation features over REST. This document collects
all operational details required to run the service in development and
production environments.

## Overview

- **Base URL:** `http://<host>:<port>` (defaults to `http://localhost:8000`)
- **API Prefix:** `/api/v1`
- **OpenAPI:** `/api/v1/openapi.json`
- **Swagger UI:** `/docs`
- **ReDoc:** `/redoc`

The FastAPI application is defined in `agdd/api/server.py` and mounts routers
for agents, runs, and GitHub webhooks. Rate limiting and authentication are
applied via shared dependencies.

## Quick Start

```bash
# Install dependencies (development + runtime)
uv sync --extra dev

# Copy configuration template and edit as needed
cp .env.example .env

# Launch the API locally
./scripts/run-api-server.sh

# Verify health
curl -sS http://localhost:8000/health | jq
```

## Authentication

Requests are authenticated with a shared secret configured via
`AGDD_API_KEY`. Clients can send the credential in either location:

- `Authorization: Bearer <token>` header (preferred)
- `x-api-key: <token>` header (fallback)

If `AGDD_API_KEY` is unset, authentication is effectively disabled—this is
suitable for local development only. Never deploy to production without a key.

## Rate Limiting

Set `AGDD_RATE_LIMIT_QPS` to enable rate limiting. Two implementations are
available:

- **In-memory:** default behavior, suitable for single-process deployments
- **Redis-backed:** supply `AGDD_REDIS_URL` to enable the distributed limiter

The Redis limiter uses an atomic Lua script with timestamp+sequence members to
avoid race conditions caused by clock granularity. When Redis is unreachable the
API fails open but emits a structured log warning.

## Configuration Matrix

| Environment Variable | Default | Description |
| --- | --- | --- |
| `AGDD_API_DEBUG` | `false` | Enables FastAPI debug/reload mode |
| `AGDD_API_HOST` | `0.0.0.0` | Bind address for the server |
| `AGDD_API_PORT` | `8000` | Listening port |
| `AGDD_API_PREFIX` | `/api/v1` | Route prefix for API routers |
| `AGDD_API_KEY` | `null` | Shared secret for authenticating clients |
| `AGDD_CORS_ORIGINS` | `["*"]` | Allowed origins; restrict for production |
| `AGDD_CORS_ALLOW_CREDENTIALS` | `false` | Enable cookies/credentials (requires specific origins) |
| `AGDD_RUNS_BASE_DIR` | `.runs/agents` | Location of run artifacts |
| `AGDD_RATE_LIMIT_QPS` | `null` | Requests per second threshold |
| `AGDD_REDIS_URL` | `null` | Enables distributed rate limiting |
| `AGDD_GITHUB_WEBHOOK_SECRET` | `null` | Webhook signature secret |
| `AGDD_GITHUB_TOKEN` | `null` | Token for posting GitHub comments |

All variables are documented inline in `agdd/api/config.py`.

## Endpoint Reference

### `GET /health`

Basic heartbeat used by orchestrators and GitHub webhooks.

**Response**

```json
{ "status": "ok" }
```

### `GET /api/v1/agents`

Lists registered agents defined in `registry/agents.yaml`.

**Response**

```json
[
  {
    "slug": "offer-orchestrator-mag",
    "title": "Offer Orchestrator",
    "description": "Coordinates compensation and candidate messaging"
  }
]
```

### `POST /api/v1/agents/{slug}/run`

Executes a MAG agent. The request payload must conform to the agent's input
contract.

**Request**

```json
{
  "payload": {
    "role": "Senior Engineer",
    "level": "Senior"
  },
  "request_id": "optional-id",
  "metadata": {
    "source": "docs-example"
  }
}
```

**Response**

```json
{
  "run_id": "mag-offer-orchestrator-mag-20250101-123456",
  "slug": "offer-orchestrator-mag",
  "output": {
    "summary": "...",
    "run_id": "mag-offer-orchestrator-mag-20250101-123456"
  },
  "artifacts": {
    "summary": "/api/v1/runs/mag-offer-orchestrator-mag-20250101-123456",
    "logs": "/api/v1/runs/mag-offer-orchestrator-mag-20250101-123456/logs"
  }
}
```

Possible error codes:

- `404` (`agent_not_found`) – slug missing from registry
- `400` (`invalid_payload` / `execution_failed`) – contract violation or runtime error
- `500` (`internal_error`) – unexpected failure (see logs)

### `GET /api/v1/runs/{run_id}`

Returns aggregated summary/metrics for a completed run. The API validates run IDs
to prevent directory traversal.

**Response**

```json
{
  "run_id": "mag-offer-orchestrator-mag-20250101-123456",
  "slug": "offer-orchestrator-mag",
  "summary": {
    "status": "success",
    "slug": "offer-orchestrator-mag"
  },
  "metrics": {
    "latency_ms": 3200,
    "total_tokens": 4500
  },
  "has_logs": true
}
```

### `GET /api/v1/runs/{run_id}/logs`

Returns run logs in NDJSON format by default. Optional parameters:

- `tail=<N>` – only stream the last N lines
- `follow=true` – enable Server-Sent Events (SSE) for live log streaming

**SSE Example**

```bash
curl -N "http://localhost:8000/api/v1/runs/<RUN_ID>/logs?follow=true&tail=20"
```

Each SSE event contains a single log line under the `data:` field.

### `POST /api/v1/github/webhook`

Receives GitHub webhook events. When a supported event contains one or more
`@agent-slug { ... }` commands, the API executes the requested agents and posts
the results back to GitHub.

Signature verification is enabled automatically when
`AGDD_GITHUB_WEBHOOK_SECRET` is configured. Unsupported events respond with `200`
and no action.

### `GET /api/v1/github/health`

Lightweight endpoint used by observability dashboards to confirm webhook health.

## Run Tracking & Observability

`agdd/api/run_tracker.py` inspects `.runs/agents/` before and after agent
execution. It reconciles results by reading `summary.json` and `metrics.json`,
falling back to directory timestamps when necessary. This mechanism ensures the
API can always return a `run_id` even when the runner does not emit one directly.

## Error Handling

Error responses follow a consistent structure:

```json
{
  "detail": {
    "code": "rate_limit_exceeded",
    "message": "Rate limit exceeded. Maximum 10 requests per second."
  }
}
```

Common scenarios:

- `401` – Missing/incorrect API key
- `404` – Unknown agent or run ID, or logs not found
- `429` – Rate limiter threshold reached
- `500` – Unhandled exception (check server logs)

## Troubleshooting

| Symptom | Resolution |
| --- | --- |
| `HTTP 401` | Verify `AGDD_API_KEY` on both server and client |
| `HTTP 404` (runs) | Confirm `.runs/agents/<RUN_ID>` exists and contains artifacts |
| `HTTP 429` | Increase `AGDD_RATE_LIMIT_QPS` or provision Redis |
| `SSE stream ends early` | Ensure the agent continues writing `logs.jsonl` and keep the connection open |
| Missing OpenAPI docs | Check `AGDD_API_PREFIX`; OpenAPI is served at `{prefix}/openapi.json` |

## Curl Cheat Sheet

The repository ships with `examples/api/curl_examples.sh`, which demonstrates
health checks, agent execution, error handling, and log streaming. Run the script
for a guided tour:

```bash
./examples/api/curl_examples.sh
```

For automated workflows see [examples/api/github_actions.yml](./examples/api/github_actions.yml).
