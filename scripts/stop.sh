#!/usr/bin/env bash
# Stop the model gateway
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose down
echo "Gateway stopped."
