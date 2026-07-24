#!/usr/bin/env bash
# Release a new version
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 0.1.0"
    exit 1
fi

VERSION="$1"
cd "$(dirname "$0")/.."

# Verify clean working tree on main
if [ -n "$(git status --porcelain)" ]; then
    echo "ERROR: Working tree is not clean."
    exit 1
fi

CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "ERROR: Must be on main branch (currently on $CURRENT_BRANCH)"
    exit 1
fi

# Verify main is up to date with origin
git fetch origin
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" != "$REMOTE" ]; then
    echo "ERROR: Local main does not match origin/main"
    echo "  Local:  $LOCAL"
    echo "  Remote: $REMOTE"
    exit 1
fi

# Run tests
echo "Running tests..."
.venv/bin/pytest -q || python -m pytest -q
.venv/bin/ruff format --check || python -m ruff format --check
.venv/bin/ruff check || python -m ruff check

# Update VERSION file
echo "$VERSION" > VERSION

# Verify CHANGELOG has the version
if ! grep -q "\[${VERSION}\]" CHANGELOG.md; then
    echo "ERROR: CHANGELOG.md does not contain version [$VERSION]"
    exit 1
fi

# Commit version files
git add VERSION CHANGELOG.md
git commit -m "release: v${VERSION}"

# Create annotated tag
git tag -a "v${VERSION}" -m "Release v${VERSION}"

# Push
git push origin main
git push origin "v${VERSION}"

echo ""
echo "Release v${VERSION} created!"
echo "Tag: v${VERSION}"
echo "Create GitHub Release at: https://github.com/AnnaTianPM/model-gateway/releases/new?tag=v${VERSION}"
