#!/bin/bash
# Cloud SQL Auth Proxy for local development
# Usage: ./scripts/cloud-sql-proxy.sh [port]
# Default port: 15432
#
# After running, connect with:
#   Host: localhost, Port: 15432, Database: dify, User: postgres

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PORT="${1:-15432}"
INSTANCE="solvook-infra:asia-northeast3:postgres-instance"
CREDENTIALS="$PROJECT_ROOT/.gcp/solvook-infra-2b84d4594582.json"

if [ ! -f "$CREDENTIALS" ]; then
    echo "Error: Credentials file not found at $CREDENTIALS"
    exit 1
fi

echo "Starting Cloud SQL Auth Proxy..."
echo "  Instance: $INSTANCE"
echo "  Port:     $PORT"
echo "  Connect:  localhost:$PORT (database: dify, user: postgres)"
echo ""
echo "Press Ctrl+C to stop."
echo ""

GOOGLE_APPLICATION_CREDENTIALS="$CREDENTIALS" \
    cloud-sql-proxy "$INSTANCE" --port="$PORT"
