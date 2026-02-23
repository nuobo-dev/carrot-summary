#!/usr/bin/env bash
# Build FlowTrack for macOS: .app bundle + .dmg disk image.
# Usage: ./scripts/build_macos.sh
# Output: dist/FlowTrack.dmg

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> Building FlowTrack for macOS..."

cd "$PROJECT_DIR"

# ── Step 1: Run PyInstaller ──────────────────────────────────────────
echo "==> Running PyInstaller..."
pyinstaller flowtrack.spec --noconfirm

# Verify the .app bundle was created
APP_PATH="$PROJECT_DIR/dist/FlowTrack.app"
if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: FlowTrack.app not found at $APP_PATH"
    exit 1
fi

echo "==> FlowTrack.app bundle created successfully."

# ── Step 2: Create .dmg disk image ──────────────────────────────────
DMG_PATH="$PROJECT_DIR/dist/FlowTrack.dmg"

# Remove existing .dmg if present
if [ -f "$DMG_PATH" ]; then
    echo "==> Removing existing FlowTrack.dmg..."
    rm -f "$DMG_PATH"
fi

echo "==> Creating FlowTrack.dmg..."
hdiutil create \
    -volname "FlowTrack" \
    -srcfolder "$APP_PATH" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

if [ ! -f "$DMG_PATH" ]; then
    echo "ERROR: Failed to create FlowTrack.dmg"
    exit 1
fi

echo "==> Build complete: $DMG_PATH"
