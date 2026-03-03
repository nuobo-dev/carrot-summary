#!/bin/bash
# Install CarrotSummary to /Applications for Spotlight access
# Usage: ./scripts/install_mac.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_PATH="$PROJECT_DIR/dist/CarrotSummary.app"
INSTALL_PATH="/Applications/CarrotSummary.app"

if [ ! -d "$APP_PATH" ]; then
    echo "🥕 App not built yet. Building..."
    cd "$PROJECT_DIR"
    bash scripts/rebuild.sh
fi

echo "🥕 Installing CarrotSummary to /Applications..."

# Remove old version if present
if [ -d "$INSTALL_PATH" ]; then
    echo "   Removing previous version..."
    rm -rf "$INSTALL_PATH"
fi

# Copy to Applications
cp -R "$APP_PATH" "$INSTALL_PATH"

# Remove quarantine flag so macOS doesn't block it
xattr -cr "$INSTALL_PATH" 2>/dev/null || true

echo ""
echo "✅ CarrotSummary installed!"
echo "   Search 'CarrotSummary' in Spotlight (Cmd+Space) to launch"
echo "   Dashboard: http://localhost:5555"
