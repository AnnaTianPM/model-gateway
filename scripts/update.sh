#!/usr/bin/env bash
# Update to a specific version
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 v0.2.0"
    exit 1
fi

VERSION="$1"
echo "Updating to $VERSION..."
exec "$(dirname "$0")/deploy.sh" "$VERSION"
