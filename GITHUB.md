# GitHub Integration Guide

The AGDD GitHub integration triggers agents from issues, pull requests, and review comments.
It posts execution results back to GitHub, providing run IDs and links to observability artifacts.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Webhook Setup](#webhook-setup)
- [Comment Syntax](#comment-syntax)
- [Response Examples](#response-examples)
- [Security](#security)
- [GitHub Actions Integration](#github-actions-integration)
- [Troubleshooting](#troubleshooting)

## Overview

- Supported events: `issue_comment`, `pull_request_review_comment`, and `pull_request`
- Comment parser understands inline commands and fenced code blocks
- Agents run inside the existing AGDD runtime (`invoke_mag`) and reuse filesystem observability
- Results are posted as comments with run IDs, artifact links, and truncated JSON output

## Prerequisites

1. Deploy the AGDD HTTP API and expose `/api/v1/github/webhook` over HTTPS.
2. Configure environment variables (see `.env.example`):
   - `AGDD_GITHUB_WEBHOOK_SECRET` – shared secret for HMAC verification
   - `AGDD_GITHUB_TOKEN` – personal access token or GitHub App token with `repo` scope
   - Optional: `AGDD_API_KEY` if webhook requests must present an API key
3. Install and authenticate the GitHub CLI (`gh`) if you plan to use the helper script.

## Webhook Setup

Use the helper script to provision the webhook via the GitHub API:

```bash
export AGDD_GITHUB_WEBHOOK_SECRET=super-secret
GITHUB_WEBHOOK_SECRET=$AGDD_GITHUB_WEBHOOK_SECRET \
  ./scripts/setup-github-webhook.sh owner/repo https://api.example.com/api/v1/github/webhook
```

The script registers the webhook for the supported event types and verifies that `gh` is authenticated.
You can also create the webhook manually in the repository settings. Ensure the following:

- **Payload URL**: `https://your-api/api/v1/github/webhook`
- **Content type**: `application/json`
- **Secret**: Matches `AGDD_GITHUB_WEBHOOK_SECRET`
- **Events**: `Issue comments`, `Pull request reviews`, and `Pull requests`

## Comment Syntax

Issue or PR comment commands must follow the pattern:

```
@agent-slug {
  "json": "payload"
}
```

- Slugs are lowercase, alphanumeric, and may include hyphens (`offer-orchestrator-mag`).
- JSON payloads must be objects and should align with the agent's input schema.
- Commands may appear inline or inside fenced ` ```json ... ``` ` code blocks.
- Multiple commands are supported within a single comment; each results in a separate execution.

## Response Examples

Successful run comment:

```
✅ **AGDD Agent `offer-orchestrator-mag` execution completed**

**Run ID**: `mag-20250101-abcdef`

**Artifacts**:
- Summary: `GET /api/v1/runs/mag-20250101-abcdef`
- Logs: `GET /api/v1/runs/mag-20250101-abcdef/logs`

**Output** (truncated):
{
  "status": "success",
  "next_steps": ["..."]
}
```

Error response when execution fails:

```
❌ **AGDD Agent `offer-orchestrator-mag` execution failed**

**Error**: `ValueError`

Invalid payload provided for offer-orchestrator-mag

**Troubleshooting**:
- Verify the agent slug exists in `registry/agents.yaml`
- Check that the JSON payload matches the agent's input schema
- Review agent implementation for runtime errors
```

## Security

- Every webhook request must include the `X-Hub-Signature-256` header. The API rejects mismatched signatures with `401`.
- GitHub webhook IP allowlisting is recommended when fronting the API with a firewall or ingress controller.
- The GitHub token is only used to post comments; it is never logged or returned in API responses.
- Rate limiting applies to webhook requests as well. Tune `AGDD_RATE_LIMIT_QPS` to absorb burst traffic from GitHub.

## GitHub Actions Integration

The repository ships with [`examples/api/github_actions.yml`](./examples/api/github_actions.yml), demonstrating two approaches:

1. **CLI Execution** – Checks out the repository, installs dependencies, and runs `agdd agent run` locally.
2. **HTTP API Execution** – Calls the deployed API using secrets `AGDD_API_URL` and `AGDD_API_KEY`, then fetches run artifacts.

Key tips:

- Store secrets as GitHub Actions repository secrets or organization secrets.
- Capture `run_id` outputs to download logs or summaries as follow-up steps.
- Combine with the webhook integration for an event-driven workflow: comments trigger executions, while Actions validate merges.

## Troubleshooting

| Symptom | Resolution |
| ------- | ---------- |
| `invalid_signature` in API logs | Ensure the webhook secret in GitHub matches `AGDD_GITHUB_WEBHOOK_SECRET`. Re-create the webhook if necessary. |
| Comment ignored | Confirm the comment body contains `@agent-slug` syntax and that the event type is supported. Edited comments are processed. |
| No response comment posted | Check that `AGDD_GITHUB_TOKEN` has `repo` scope. The API logs a warning when posting fails. |
| Execution succeeds but run_id missing | The API falls back to filesystem detection; ensure `.runs/agents/` is writable and not mounted read-only. |
| Rate limit exceeded | Increase `AGDD_RATE_LIMIT_QPS` or configure Redis using `AGDD_REDIS_URL` for distributed deployments. |

For deeper diagnostics enable FastAPI debug logging and tail API logs while triggering commands.
