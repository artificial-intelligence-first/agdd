# GitHub Integration Guide

AGDD ships with a GitHub webhook bridge that executes agents from pull request or issue comments and posts the results back to the originating thread. This guide explains the end-to-end setup, supported commands, and troubleshooting steps.

## Prerequisites

- Deployed AGDD HTTP API with `/api/v1/github/webhook` reachable from GitHub
- `AGDD_GITHUB_WEBHOOK_SECRET` configured in both GitHub and the API server
- `AGDD_GITHUB_TOKEN` with `repo` scope (for posting comments)
- Optional: `AGDD_API_KEY` if the API server requires authentication for outbound artifact links

## Webhook Setup

Use the helper script to create or update the webhook:

```bash
GITHUB_WEBHOOK_SECRET="your-secret" \
./scripts/setup-github-webhook.sh owner/repo https://api.example.com/api/v1/github/webhook
```

The script verifies `gh` authentication and registers the webhook for the following events:

- `issue_comment`
- `pull_request_review_comment`
- `pull_request`

You can also configure the webhook manually in the repository settings. Ensure the **content type** is `application/json` and the secret matches `AGDD_GITHUB_WEBHOOK_SECRET` on the server.

## Comment Syntax

Agent executions are triggered with an `@agent-slug` mention followed by JSON payload enclosed in braces:

```
@offer-orchestrator-mag {
  "role": "Senior Engineer",
  "level": "Senior",
  "experience_years": 8
}
```

Multiple commands can be provided in a single comment or PR body; each is executed sequentially.

Commands are parsed both inline and within fenced code blocks labelled `json`:

````json
@compensation-advisor-sag {
  "candidate_profile": {
    "role": "Staff Engineer",
    "location": "Remote - US"
  }
}
````

## Response Comments

The integration posts rich feedback summarizing the run outcome.

### Success Example

> ✅ **AGDD Agent `offer-orchestrator-mag` execution completed**
>
> **Run ID**: `mag-20240101-abcdef`
>
> **Artifacts**:
> - Summary: `GET /api/v1/runs/mag-20240101-abcdef`
> - Logs: `GET /api/v1/runs/mag-20240101-abcdef/logs`
>
> **Output** (truncated):
>
> ```json
> {"offer": {"role": "Senior Engineer"}}
> ```

### Failure Example

> ❌ **AGDD Agent `offer-orchestrator-mag` execution failed**
>
> **Error**: `ValueError`
>
> ```
> Payload validation failed
> ```
>
> **Troubleshooting**:
> - Verify the agent slug exists in `registry/agents.yaml`
> - Check that the JSON payload matches the agent's input schema
> - Review agent implementation for runtime errors

## Security Considerations

- Every request is authenticated via the `X-Hub-Signature-256` header using HMAC SHA-256. Invalid signatures return HTTP 401.
- API keys are never required for inbound webhooks (GitHub cannot set custom Authorization headers), but artifact links include bearer-protected endpoints. Configure `AGDD_API_KEY` if the links should be private.
- Webhook handlers gracefully handle missing `AGDD_GITHUB_TOKEN` by skipping comment replies to avoid blocking the event pipeline.

## GitHub Actions Integration

The repository includes [`examples/api/github_actions.yml`](./examples/api/github_actions.yml) with two primary jobs:

1. **CLI execution:** Checks out the repo, installs dependencies with `uv`, and runs `agdd agent run` locally.
2. **API execution:** Calls the HTTP API using secrets `AGDD_API_URL` and `AGDD_API_KEY`, then fetches run summaries and logs.

Use the workflow as a template for scheduled automations or manual triggers.

## Troubleshooting

| Symptom | Diagnosis | Resolution |
| --- | --- | --- |
| Webhook returns 401 | Signature mismatch | Confirm `AGDD_GITHUB_WEBHOOK_SECRET` matches GitHub settings |
| No comment posted | Missing `AGDD_GITHUB_TOKEN` | Configure a token with `repo` scope on the API server |
| Agent not triggered | Command not detected | Ensure `@agent-slug {json}` syntax is outside quoted text or fenced code blocks |
| Rate limit warnings | Burst of events | Increase `AGDD_RATE_LIMIT_QPS` or enable Redis-backed limiter |
| Comment posts succeed but artifacts 401 | API key enforced | Share `AGDD_API_KEY` with human reviewers or host artifacts without auth |

## Monitoring

- Check `/api/v1/github/health` for a lightweight readiness probe.
- Enable FastAPI logging (`AGDD_API_DEBUG=1`) during development to inspect incoming payloads (secrets are never logged).
- The webhook handlers log failures to post comments via Python's standard logging facility; ensure your deployment collects WARN level logs.

For deeper HTTP API behaviour, refer back to [API Usage Guide](./api-usage.md).
