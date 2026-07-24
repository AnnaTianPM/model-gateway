#!/usr/bin/env bash
# Deploy a specific version
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 v0.1.0"
    exit 1
fi

VERSION="$1"
cd "$(dirname "$0")/.."

# Verify git tag exists
TAG="${VERSION#v}"
if ! git rev-parse "v${TAG}" > /dev/null 2>&1; then
    echo "ERROR: Git tag v${TAG} does not exist"
    exit 1
fi

# Verify working tree is clean
if [ -n "$(git status --porcelain)" ]; then
    echo "ERROR: Working tree is not clean. Commit or stash changes first."
    exit 1
fi

COMMIT=$(git rev-parse --short "v${TAG}")
echo "Deploying version $VERSION (commit $COMMIT)..."

# Check out the tag
git checkout "v${TAG}"

# Backup before deploy
echo "Creating pre-deployment backup..."
./scripts/backup.sh

# Build and start
export APP_VERSION="$TAG"
export GIT_COMMIT="$COMMIT"
echo "Building Docker image..."
docker compose up -d --build

# Wait for health
echo "Waiting for health check..."
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8000/health/live > /dev/null 2>&1; then
        echo "Gateway is healthy!"
        break
    fi
    sleep 2
done

# Smoke test
echo "Running smoke test..."
if curl -sf http://127.0.0.1:8000/health/live > /dev/null 2>&1; then
    echo "Smoke test PASSED."
    echo "Deployed $VERSION successfully."
else
    echo "Smoke test FAILED. Rolling back..."
    ./scripts/rollback.sh
    exit 1
fi
