#!/usr/bin/env bash
# Build CarrotSummary for macOS: .app bundle + .dmg disk image.
# Usage: ./scripts/build_macos.sh
# Output: dist/CarrotSummary.dmg

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> Building CarrotSummary for macOS..."

cd "$PROJECT_DIR"

# ── Step 1: Run PyInstaller ──────────────────────────────────────────
echo "==> Running PyInstaller..."
pyinstaller flowtrack.spec --noconfirm

# Verify the .app bundle was created
APP_PATH="$PROJECT_DIR/dist/CarrotSummary.app"
if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: CarrotSummary.app not found at $APP_PATH"
    exit 1
fi

echo "==> CarrotSummary.app bundle created successfully."

# ── Step 2: Create .dmg disk image ──────────────────────────────────
DMG_PATH="$PROJECT_DIR/dist/CarrotSummary.dmg"

# Remove existing .dmg if present
if [ -f "$DMG_PATH" ]; then
    echo "==> Removing existing CarrotSummary.dmg..."
    rm -f "$DMG_PATH"
fi

echo "==> Creating CarrotSummary.dmg..."
hdiutil create \
    -volname "CarrotSummary" \
    -srcfolder "$APP_PATH" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

if [ ! -f "$DMG_PATH" ]; then
    echo "ERROR: Failed to create CarrotSummary.dmg"
    exit 1
fi

echo "==> Build complete: $DMG_PATH"
