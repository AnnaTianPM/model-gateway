#!/usr/bin/env bash
# Rollback to a specific version
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 v0.1.0"
    exit 1
fi

VERSION="$1"
cd "$(dirname "$0")/.."

TAG="${VERSION#v}"
if ! git rev-parse "v${TAG}" > /dev/null 2>&1; then
    echo "ERROR: Git tag v${TAG} does not exist"
    exit 1
fi

COMMIT=$(git rev-parse --short "v${TAG}")
echo "Rolling back to $VERSION (commit $COMMIT)..."

# Stop current
echo "Stopping current version..."
docker compose down

# Find the most recent backup before this version
LATEST_BACKUP=$(ls -d backups/* 2>/dev/null | sort -r | head -1 || true)
if [ -n "$LATEST_BACKUP" ]; then
    echo "Restoring from backup: $LATEST_BACKUP"
    ./scripts/restore.sh "$LATEST_BACKUP"
else
    echo "WARNING: No backup found. Starting with fresh database."
fi

# Checkout target version
git checkout "v${TAG}"

# Build and start
export APP_VERSION="$TAG"
export GIT_COMMIT="$COMMIT"
echo "Building Docker image..."
docker compose up -d --build

# Wait for health
echo "Waiting for health check..."
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8000/health/live > /dev/null 2>&1; then
        echo "Gateway is healthy after rollback!"
        echo "Rolled back to $VERSION successfully."
        exit 0
    fi
    sleep 2
done

echo "ERROR: Gateway did not become healthy after rollback"
docker compose logs --tail 50 gateway
exit 1
