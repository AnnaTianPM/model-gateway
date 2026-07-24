#!/usr/bin/env bash
# Backup the model gateway database and config
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION=$(cat VERSION 2>/dev/null || echo "unknown")
COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
TIMESTAMP=$(date -u +%Y%m%dT%H%M%S)
BACKUP_DIR="backups/${TIMESTAMP}_v${VERSION}_${COMMIT}"

mkdir -p "$BACKUP_DIR"

# Backup SQLite database
if [ -f data/gateway.db ]; then
    cp data/gateway.db "$BACKUP_DIR/gateway.db"
    echo "Backed up database to $BACKUP_DIR/gateway.db"
else
    echo "WARNING: No database file found at data/gateway.db"
fi

# Backup config
if [ -f config/local-overrides.yaml ]; then
    cp config/local-overrides.yaml "$BACKUP_DIR/local-overrides.yaml"
fi

# Backup VERSION
cp VERSION "$BACKUP_DIR/VERSION" 2>/dev/null || true

# Create manifest
cat > "$BACKUP_DIR/manifest.json" << EOF
{
    "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "app_version": "$VERSION",
    "git_commit": "$COMMIT",
    "docker_image": "model-gateway:$VERSION"
}
EOF

# Generate checksums
cd "$BACKUP_DIR"
find . -type f ! -name "checksums.sha256" -exec sha256sum {} \; > checksums.sha256

echo ""
echo "Backup completed: $BACKUP_DIR"
echo "Manifest: $BACKUP_DIR/manifest.json"
echo "Checksums: $BACKUP_DIR/checksums.sha256"
