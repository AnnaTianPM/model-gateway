#!/usr/bin/env bash
# Restore from a backup directory
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup_dir>"
    echo "Example: $0 backups/20260724T210500_v0.1.0_abc1234"
    exit 1
fi

BACKUP_DIR="$1"
cd "$(dirname "$0")/.."

if [ ! -d "$BACKUP_DIR" ]; then
    echo "ERROR: Backup directory not found: $BACKUP_DIR"
    exit 1
fi

# Verify checksums
cd "$BACKUP_DIR"
if [ -f checksums.sha256 ]; then
    sha256sum -c checksums.sha256 || {
        echo "ERROR: Checksum verification failed!"
        exit 1
    }
    echo "Checksums verified."
fi
cd - > /dev/null

# Stop gateway
echo "Stopping gateway..."
docker compose down

# Restore database
if [ -f "$BACKUP_DIR/gateway.db" ]; then
    cp "$BACKUP_DIR/gateway.db" data/gateway.db
    echo "Restored database."
fi

# Restore config
if [ -f "$BACKUP_DIR/local-overrides.yaml" ]; then
    cp "$BACKUP_DIR/local-overrides.yaml" config/local-overrides.yaml
    echo "Restored config."
fi

# Restart
echo "Starting gateway..."
docker compose up -d --build

echo "Restore completed."
