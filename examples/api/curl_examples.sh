#!/usr/bin/env bash
# Example curl commands for AGDD HTTP API

set -euo pipefail

# API base URL
API_URL="${API_URL:-http://localhost:8000}"
API_PREFIX="/api/v1"

# Optional API key
API_KEY="${AGDD_API_KEY:-}"
AUTH_HEADER=""
if [ -n "$API_KEY" ]; then
    AUTH_HEADER="-H \"Authorization: Bearer $API_KEY\""
fi

echo "AGDD HTTP API Examples"
echo "======================"
echo "API URL: $API_URL$API_PREFIX"
echo ""

# Health check
echo "1. Health Check"
echo "   curl -sS $API_URL/health | jq"
curl -sS "$API_URL/health" | jq
echo ""

# List agents
echo "2. List Registered Agents"
echo "   curl -sS $API_URL$API_PREFIX/agents $AUTH_HEADER | jq"
eval curl -sS "$API_URL$API_PREFIX/agents" $AUTH_HEADER | jq
echo ""

# Run agent example
echo "3. Run Agent (offer-orchestrator-mag)"
echo "   curl -sS -X POST $API_URL$API_PREFIX/agents/offer-orchestrator-mag/run \\"
echo "        $AUTH_HEADER \\"
echo "        -H \"Content-Type: application/json\" \\"
echo "        -d '{\"payload\": {\"role\":\"Senior Engineer\",\"level\":\"Senior\",\"experience_years\":8}}' | jq"
echo ""
echo "Example:"
eval curl -sS -X POST "$API_URL$API_PREFIX/agents/offer-orchestrator-mag/run" \
     $AUTH_HEADER \
     -H "Content-Type: application/json" \
     -d '{"payload": {"role":"Senior Engineer","level":"Senior","experience_years":8}}' | jq '.run_id, .slug'
echo ""

# Get run summary (requires run_id from previous step)
echo "4. Get Run Summary"
echo "   RUN_ID=<run-id-from-step-3>"
echo "   curl -sS $API_URL$API_PREFIX/runs/\$RUN_ID $AUTH_HEADER | jq"
echo ""

# Get run logs
echo "5. Get Run Logs"
echo "   curl -sS $API_URL$API_PREFIX/runs/\$RUN_ID/logs $AUTH_HEADER"
echo ""

# Stream logs (SSE)
echo "6. Stream Logs (Server-Sent Events)"
echo "   curl -sS $API_URL$API_PREFIX/runs/\$RUN_ID/logs?follow=true $AUTH_HEADER"
echo ""

# Get logs tail
echo "7. Get Last 10 Log Lines"
echo "   curl -sS $API_URL$API_PREFIX/runs/\$RUN_ID/logs?tail=10 $AUTH_HEADER"
echo ""

echo "For more details, see: $API_URL/docs"
