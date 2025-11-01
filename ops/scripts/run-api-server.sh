#!/usr/bin/env bash
# Start the MAGSAG HTTP API server

set -euo pipefail

# Default values
HOST="${MAGSAG_API_HOST:-0.0.0.0}"
PORT="${MAGSAG_API_PORT:-8000}"
RELOAD="${MAGSAG_API_DEBUG:-false}"

echo "Starting MAGSAG API server..."
echo "Host: $HOST"
echo "Port: $PORT"
echo "Reload: $RELOAD"

if [ "$RELOAD" = "true" ]; then
    uv run uvicorn magsag.api.server:app --host "$HOST" --port "$PORT" --reload
else
    uv run uvicorn magsag.api.server:app --host "$HOST" --port "$PORT"
fi
