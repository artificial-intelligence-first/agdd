# AGDD GitHub Integration Guide

The AGDD GitHub integration allows teams to trigger agents directly from issues, pull requests, and review comments. This guide documents the webhook workflow, security requirements, and troubleshooting steps.

## Overview

- Webhook endpoint: `POST /api/v1/github/webhook`
- Supported events: `issue_comment`, `pull_request_review_comment`, `pull_request`
- Response comments reference API artifacts and include success/failure summaries
- Health probe: `GET /api/v1/github/health`

## Prerequisites

- Deployed AGDD HTTP API (see [API.md](./API.md))
- Environment variables configured:
  - `AGDD_GITHUB_WEBHOOK_SECRET` – shared secret for signature verification
  - `AGDD_GITHUB_TOKEN` – GitHub token with `public_repo` or equivalent issue/PR write scope
  - `AGDD_RUNS_BASE_DIR` (optional) – override `.runs/agents` storage location
- `AGDD_API_KEY` recommended so webhook invocations and manual API usage share the same auth controls

## Webhook Setup

1. Deploy or port-forward your API server so GitHub can reach `/api/v1/github/webhook`.
2. Run the helper script:

   ```bash
   GITHUB_WEBHOOK_SECRET=<secret> \
     ./scripts/setup-github-webhook.sh owner/repo https://api.example.com/api/v1/github/webhook
   ```

   The script validates `gh` CLI authentication, creates the webhook, and subscribes to all supported events.

3. Store the same secret in your deployment environment as `AGDD_GITHUB_WEBHOOK_SECRET`.
4. Provide a GitHub token with permission to post comments (e.g., a fine-grained PAT or GitHub App installation token) via `AGDD_GITHUB_TOKEN`.
5. Test the integration by posting a comment that references an agent slug (see below).

To manage hooks manually, use `gh api repos/<owner>/<repo>/hooks` and `gh api -X DELETE ...` for cleanup.

## Comment Syntax

Use `@<agent-slug> { ...json payload... }`. Slugs must match registry entries. Commands can appear inline or inside fenced code blocks (for example, `\`\`\`json ... \`\`\``).

Example:

```
@offer-orchestrator-mag {
  "role": "Staff Engineer",
  "level": "Staff",
  "experience_years": 12
}
```

Multiple commands per comment are supported. Invalid JSON payloads are ignored to avoid spurious failures.

## Event Handling Flow

1. Webhook handler verifies the `X-Hub-Signature-256` header when a secret is configured.
2. Commands are parsed from the comment body, review comment, or PR description using a JSON decoder that supports nested objects.
3. Each command triggers `invoke_mag` in a thread pool with filesystem snapshots for run tracking.
4. Results are posted back to the originating issue/PR as comments:
   - ✅ Success comments include the `run_id`, links to `/api/v1/runs/{run_id}`, and truncated output.
   - ❌ Failure comments include the exception type, message, and troubleshooting guidance.

## GitHub Actions Integration

Combine webhooks with CI workflows for deterministic automation. The repository ships an example workflow at [`examples/api/github_actions.yml`](./examples/api/github_actions.yml) that demonstrates both CLI and HTTP API execution from a manual dispatch.

Key tips:

- Store `AGDD_API_URL` and `AGDD_API_KEY` as encrypted secrets.
- Capture `run_id` outputs and use follow-up steps to fetch summaries and logs.
- Surface failures with `::error::` annotations so they appear in the Actions UI.

## Security Considerations

- Always set `AGDD_GITHUB_WEBHOOK_SECRET` to enforce HMAC validation.
- Keep `AGDD_GITHUB_TOKEN` scoped to the minimal repositories and permissions required.
- Restrict `CORS_ORIGINS` and require `AGDD_API_KEY` for all API traffic, including webhook callbacks.
- Review logs (`agdd.api.rate_limit` warnings) to ensure Redis-based limits are functioning across deployments.

## Troubleshooting

| Symptom | Resolution |
| --- | --- |
| `401 invalid_signature` in webhook response | Verify the secret configured in GitHub matches `AGDD_GITHUB_WEBHOOK_SECRET`. Regenerate if necessary. |
| No comment posted after command | Ensure `AGDD_GITHUB_TOKEN` is set and has issue/PR write access. Token failures are swallowed to keep webhook delivery successful, so inspect server logs. |
| Agent executes but `run_id` missing | Confirm `.runs/agents` is writable and the observability logger emits summaries. The API falls back to newest MAG directory when summaries are unavailable. |
| `429 rate_limit_exceeded` | Increase `AGDD_RATE_LIMIT_QPS` or configure Redis for distributed rate limiting if multiple webhook workers are active. |
| Payload ignored | Check JSON validity and ensure the slug matches `registry/agents.yaml` (case-sensitive, lowercase). |

For more details on the webhook implementation, review `agdd/integrations/github/webhook.py` and the integration tests in `tests/integration/test_api_github.py`.
