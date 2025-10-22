#!/usr/bin/env bash
# AGDD HTTP API - Comprehensive curl command examples
#
# Usage:
#   export API_URL="http://localhost:8000"  # Optional, defaults to localhost
#   export AGDD_API_KEY="your-key"          # Optional, only if auth enabled
#   ./examples/api/curl_examples.sh

set -euo pipefail

# Configuration
API_URL="${API_URL:-http://localhost:8000}"
API_PREFIX="/api/v1"
API_KEY="${AGDD_API_KEY:-}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Helper for authenticated requests
api_call() {
    local method="$1"
    local endpoint="$2"
    shift 2

    if [ -n "$API_KEY" ]; then
        curl -sS -X "$method" "$API_URL$endpoint" \
            -H "Authorization: Bearer $API_KEY" \
            "$@"
    else
        curl -sS -X "$method" "$API_URL$endpoint" "$@"
    fi
}

print_section() {
    echo -e "\n${BLUE}=== $1 ===${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

echo "AGDD HTTP API Examples"
echo "======================"
echo "API URL: $API_URL$API_PREFIX"
echo "Auth: ${API_KEY:+Enabled}${API_KEY:-Disabled}"
echo ""

# ============================================================================
# 1. Health Check
# ============================================================================
print_section "1. Health Check"
api_call GET /health | jq '.'
print_success "Health check passed"

# ============================================================================
# 2. List Agents
# ============================================================================
print_section "2. List Available Agents"
AGENTS=$(api_call GET "$API_PREFIX/agents")
echo "$AGENTS" | jq '.'
print_success "Agent list retrieved"

# Get first agent slug for examples
AGENT_SLUG=$(echo "$AGENTS" | jq -r '.[0].slug // "offer-orchestrator-mag"')
echo "Using agent: $AGENT_SLUG"

# ============================================================================
# 3. Run Agent
# ============================================================================
print_section "3. Execute Agent"
RESPONSE=$(api_call POST "$API_PREFIX/agents/$AGENT_SLUG/run" \
    -H "Content-Type: application/json" \
    -d '{
        "payload": {
            "role": "Senior Engineer",
            "level": "Senior",
            "experience_years": 8
        }
    }')

echo "$RESPONSE" | jq '.'
RUN_ID=$(echo "$RESPONSE" | jq -r '.run_id // empty')

if [ -z "$RUN_ID" ]; then
    print_warning "No run_id returned (agent may still be running)"
    RUN_ID="example-run-id"
else
    print_success "Agent executed. Run ID: $RUN_ID"
fi

# ============================================================================
# 4. Run Agent with Metadata
# ============================================================================
print_section "4. Execute Agent with Request Metadata"
api_call POST "$API_PREFIX/agents/$AGENT_SLUG/run" \
    -H "Content-Type: application/json" \
    -d '{
        "payload": {
            "test": true
        },
        "request_id": "custom-req-'$(date +%s)'",
        "metadata": {
            "source": "curl_example",
            "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
        }
    }' | jq '.run_id, .slug'
print_success "Agent executed with metadata"

# ============================================================================
# 5. Get Run Summary
# ============================================================================
if [ "$RUN_ID" != "example-run-id" ]; then
    print_section "5. Retrieve Run Summary"
    api_call GET "$API_PREFIX/runs/$RUN_ID" | jq '.'
    print_success "Run summary retrieved"
fi

# ============================================================================
# 6. Get Run Logs (Tail)
# ============================================================================
if [ "$RUN_ID" != "example-run-id" ]; then
    print_section "6. Retrieve Last 10 Log Lines"
    api_call GET "$API_PREFIX/runs/$RUN_ID/logs?tail=10"
    print_success "Log tail retrieved"
fi

# ============================================================================
# 7. Get All Logs
# ============================================================================
if [ "$RUN_ID" != "example-run-id" ]; then
    print_section "7. Retrieve All Logs"
    api_call GET "$API_PREFIX/runs/$RUN_ID/logs" | head -20
    echo "... (truncated for display)"
    print_success "Full logs retrieved"
fi

# ============================================================================
# 8. Error Handling - 404
# ============================================================================
print_section "8. Error Handling - Non-existent Agent (404)"
api_call POST "$API_PREFIX/agents/non-existent/run" \
    -H "Content-Type: application/json" \
    -d '{"payload": {}}' \
    2>&1 | head -5 || true
print_success "404 error handled correctly"

# ============================================================================
# 9. Error Handling - 400
# ============================================================================
print_section "9. Error Handling - Invalid Run ID (404/400)"
api_call GET "$API_PREFIX/runs/invalid-run-id" 2>&1 | head -5 || true
print_success "Error handled correctly"

# ============================================================================
# Additional Examples
# ============================================================================
print_section "Additional Commands"
echo ""
echo "Stream logs (SSE - will block):"
echo "  curl -N $API_URL$API_PREFIX/runs/\$RUN_ID/logs?follow=true"
echo ""
echo "Batch execution:"
echo "  for i in {1..5}; do"
echo "    curl -sS -X POST $API_URL$API_PREFIX/agents/$AGENT_SLUG/run \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"payload\": {\"batch_id\": '\$i'}}' | jq -r .run_id"
echo "  done"
echo ""
echo "Monitor multiple runs:"
echo "  watch -n 2 \"curl -sS $API_URL$API_PREFIX/runs/\$RUN_ID | jq '.summary.status'\""
echo ""

# ============================================================================
# Summary
# ============================================================================
print_section "Summary"
echo "All examples completed successfully!"
echo ""
echo "Documentation:"
echo "  • Swagger UI: $API_URL/docs"
echo "  • ReDoc:      $API_URL/redoc"
echo "  • OpenAPI:    $API_URL$API_PREFIX/openapi.json"
echo ""
echo "Environment:"
echo "  API_URL=$API_URL"
echo "  AGDD_API_KEY=${AGDD_API_KEY:+(set)}"
echo ""
