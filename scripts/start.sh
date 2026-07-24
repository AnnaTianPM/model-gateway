#!/usr/bin/env bash
# Start the model gateway (first-time setup)
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "IMPORTANT: Edit .env to set ADMIN_TOKEN and GATEWAY_MASTER_KEY"
fi

echo "Building and starting model gateway..."
docker compose up -d --build

echo ""
echo "Waiting for health check..."
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8000/health/live > /dev/null 2>&1; then
        echo "Gateway is healthy!"
        echo "Dashboard: http://localhost:8000/"
        echo "API:       http://localhost:8000/v1/"
        exit 0
    fi
    sleep 2
done

echo "ERROR: Gateway did not become healthy within 60 seconds"
docker compose logs --tail 50 gateway
exit 1
