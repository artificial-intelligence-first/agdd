#!/usr/bin/env bash
# Setup GitHub webhook for AGDD API integration
#
# Usage:
#   GITHUB_WEBHOOK_SECRET=your-secret ./scripts/setup-github-webhook.sh owner/repo https://your-api.com
#
# Requirements:
#   - gh CLI installed and authenticated
#   - GITHUB_WEBHOOK_SECRET environment variable set

set -euo pipefail

# Check arguments
if [ $# -lt 2 ]; then
    echo "Usage: $0 <owner/repo> <webhook-url>"
    echo ""
    echo "Example:"
    echo "  GITHUB_WEBHOOK_SECRET=my-secret $0 owner/repo https://api.example.com/api/v1/github/webhook"
    exit 1
fi

REPO="$1"
WEBHOOK_URL="$2"
SECRET="${GITHUB_WEBHOOK_SECRET:?GITHUB_WEBHOOK_SECRET environment variable is required}"

# Check gh CLI
if ! command -v gh &> /dev/null; then
    echo "Error: gh CLI is not installed"
    echo "Install from: https://cli.github.com/"
    exit 1
fi

# Check authentication
if ! gh auth status &> /dev/null; then
    echo "Error: gh CLI is not authenticated"
    echo "Run: gh auth login"
    exit 1
fi

echo "Setting up GitHub webhook..."
echo "Repository: $REPO"
echo "Webhook URL: $WEBHOOK_URL"
echo ""

# Create webhook
gh api repos/"$REPO"/hooks \
    -f name=web \
    -F active=true \
    -f events='["issue_comment", "pull_request_review_comment", "pull_request"]' \
    -F config[url]="$WEBHOOK_URL" \
    -F config[content_type]=json \
    -F config[secret]="$SECRET" \
    -F config[insecure_ssl]=0

echo ""
echo "✅ Webhook created successfully!"
echo ""
echo "Next steps:"
echo "1. Ensure your API server has AGDD_GITHUB_WEBHOOK_SECRET=$SECRET"
echo "2. Ensure your API server has AGDD_GITHUB_TOKEN=<your-github-token>"
echo "3. Test by commenting '@agent-slug {\"test\": true}' on an issue"
echo ""
echo "To list webhooks:"
echo "  gh api repos/$REPO/hooks"
echo ""
echo "To delete webhook:"
echo "  gh api -X DELETE repos/$REPO/hooks/<hook-id>"
