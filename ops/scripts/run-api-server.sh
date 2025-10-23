#!/usr/bin/env bash
# Start the AGDD HTTP API server

set -euo pipefail

# Default values
HOST="${AGDD_API_HOST:-0.0.0.0}"
PORT="${AGDD_API_PORT:-8000}"
RELOAD="${AGDD_API_DEBUG:-false}"

echo "Starting AGDD API server..."
echo "Host: $HOST"
echo "Port: $PORT"
echo "Reload: $RELOAD"

if [ "$RELOAD" = "true" ]; then
    uv run uvicorn agdd.api.server:app --host "$HOST" --port "$PORT" --reload
else
    uv run uvicorn agdd.api.server:app --host "$HOST" --port "$PORT"
fi
