#!/bin/bash
# Rebuild FlowTrack standalone app after code changes.
# Usage: ./scripts/rebuild.sh
# Output: dist/FlowTrack.app and dist/FlowTrack.dmg

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

echo "🥕 Rebuilding FlowTrack..."

# Step 1: Install/update dependencies
echo "==> Installing dependencies..."
pip3 install -r requirements.txt pyinstaller --break-system-packages -q 2>/dev/null || \
pip3 install -r requirements.txt pyinstaller -q

# Step 2: Run tests
echo "==> Running tests..."
python3 -m pytest -q --tb=short || {
    echo "❌ Tests failed. Fix them before rebuilding."
    exit 1
}

# Step 3: Build .app bundle
echo "==> Building .app bundle..."
pyinstaller flowtrack.spec --noconfirm --log-level WARN

if [ ! -d "dist/FlowTrack.app" ]; then
    echo "❌ Build failed — FlowTrack.app not found."
    exit 1
fi

# Step 4: Create .dmg
echo "==> Creating .dmg installer..."
rm -f dist/FlowTrack.dmg
hdiutil create \
    -volname "FlowTrack" \
    -srcfolder dist/FlowTrack.app \
    -ov \
    -format UDZO \
    dist/FlowTrack.dmg \
    -quiet

if [ ! -f "dist/FlowTrack.dmg" ]; then
    echo "❌ Failed to create FlowTrack.dmg"
    exit 1
fi

APP_SIZE=$(du -sh dist/FlowTrack.app | cut -f1)
DMG_SIZE=$(du -sh dist/FlowTrack.dmg | cut -f1)

echo ""
echo "✅ Build complete!"
echo "   App:       dist/FlowTrack.app  ($APP_SIZE)"
echo "   Installer: dist/FlowTrack.dmg  ($DMG_SIZE)"
echo ""
echo "   To test: open dist/FlowTrack.app"
echo "   To distribute: share dist/FlowTrack.dmg"
