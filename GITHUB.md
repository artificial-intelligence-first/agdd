# AGDD GitHub Integration Guide

This guide explains how to connect GitHub to the AG-Driven Development (AGDD)
HTTP API so engineers can launch agents directly from issues, pull requests, and
workflows.

## Overview

- **Webhook endpoint:** `POST /api/v1/github/webhook`
- **Supported events:** `issue_comment`, `pull_request_review_comment`, `pull_request`
- **Command syntax:** `@agent-slug {"json": "payload"}` (supports inline and fenced code blocks)
- **Response:** Success/failure comment posted with run ID and artifact links

The webhook handler lives in `agdd/api/routes/github.py` and delegates to
`agdd/integrations/github/webhook.py` for execution and response formatting.

## Prerequisites

1. Deploy the AGDD HTTP API (see [API.md](./API.md))
2. Configure the following environment variables in `.env`:
   - `AGDD_GITHUB_WEBHOOK_SECRET` – shared secret to verify incoming payloads
   - `AGDD_GITHUB_TOKEN` – token with `repo` scope to post comments
3. Confirm the API is reachable from GitHub over HTTPS

## Webhook Setup

Use the provided helper script to create the webhook with the correct events and
secret:

```bash
GITHUB_WEBHOOK_SECRET=<secret> \
./scripts/setup-github-webhook.sh owner/repo https://api.example.com/api/v1/github/webhook
```

The script verifies that the GitHub CLI (`gh`) is installed and authenticated.
It registers the webhook for all supported events and configures SSL validation.

### Manual Setup (Optional)

If you prefer the GitHub UI:

1. Navigate to **Settings → Webhooks** for the repository
2. Click **Add webhook**
3. URL: `https://api.example.com/api/v1/github/webhook`
4. Content type: `application/json`
5. Secret: your webhook secret
6. Events: select *Let me select individual events* and enable:
   - Issue comments
   - Pull request review comments
   - Pull requests
7. Save the webhook

## Comment Syntax

A comment triggers execution when it contains one or more commands in the form:

```
@agent-slug {
  "key": "value"
}
```

- `agent-slug` must match an entry in `registry/agents.yaml`
- The payload must be valid JSON (objects only)
- Multiple commands can appear in a single comment or PR body
- Commands can also be placed inside fenced code blocks marked with `json`

Examples:

- `@offer-orchestrator-mag {"role": "Staff Engineer", "level": "Staff"}`
- ```json
  @compensation-advisor-sag {
    "candidate": "Ada Lovelace",
    "target_level": "Principal"
  }
  ```

## Execution Flow

1. GitHub sends an event payload with the webhook secret signature
2. `agdd/api/routes/github.py` validates the HMAC SHA-256 signature
3. Commands are parsed by `agdd/integrations/github/comment_parser.py`
4. Each command executes via `invoke_mag` in a background thread
5. Run artifacts are correlated using `agdd/api/run_tracker.py`
6. A formatted success or failure comment is posted back to GitHub

## Response Comments

### Success

```
✅ **AGDD Agent `offer-orchestrator-mag` execution completed**

**Run ID**: `mag-offer-orchestrator-mag-20250101-123456`

**Artifacts**:
- Summary: `GET /api/v1/runs/mag-offer-orchestrator-mag-20250101-123456`
- Logs: `GET /api/v1/runs/mag-offer-orchestrator-mag-20250101-123456/logs`

**Output** (truncated):
```json
{...}
```
```

### Failure

```
❌ **AGDD Agent `offer-orchestrator-mag` execution failed**

**Error**: `ValueError`

```

## GitHub Actions Integration

Two automation patterns are provided in
[examples/api/github_actions.yml](./examples/api/github_actions.yml):

1. Run agents locally via the CLI
2. Invoke the HTTP API directly (useful for remote deployments)

The workflow extracts `run_id` values for downstream steps and demonstrates how
to fetch summaries and logs.

## Troubleshooting

| Symptom | Resolution |
| --- | --- |
| `401 invalid_signature` | Verify `AGDD_GITHUB_WEBHOOK_SECRET` matches the webhook configuration |
| No comment posted | Confirm `AGDD_GITHUB_TOKEN` has `repo` scope and is not rate limited |
| Agent not found | Check that the slug exists in `registry/agents.yaml` |
| Payload parsing skipped | Ensure the payload is valid JSON and commands use lowercase slugs |
| Duplicate executions | GitHub may retry failed deliveries; use idempotent agent logic when possible |

For deeper debugging, inspect the API server logs. Signature validation failures
return `401` to GitHub and will appear in the webhook delivery history.
