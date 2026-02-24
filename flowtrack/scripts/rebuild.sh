#!/bin/bash
# Rebuild CarrotSummary standalone app after code changes.
# Usage: ./scripts/rebuild.sh
# Output: dist/CarrotSummary.app and dist/CarrotSummary.dmg

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

echo "🥕 Rebuilding CarrotSummary..."

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

if [ ! -d "dist/CarrotSummary.app" ]; then
    echo "❌ Build failed — CarrotSummary.app not found."
    exit 1
fi

# Step 4: Create .dmg
echo "==> Creating .dmg installer..."
rm -f dist/CarrotSummary.dmg
hdiutil create \
    -volname "CarrotSummary" \
    -srcfolder dist/CarrotSummary.app \
    -ov \
    -format UDZO \
    dist/CarrotSummary.dmg \
    -quiet

if [ ! -f "dist/CarrotSummary.dmg" ]; then
    echo "❌ Failed to create CarrotSummary.dmg"
    exit 1
fi

APP_SIZE=$(du -sh dist/CarrotSummary.app | cut -f1)
DMG_SIZE=$(du -sh dist/CarrotSummary.dmg | cut -f1)

echo ""
echo "✅ Build complete!"
echo "   App:       dist/CarrotSummary.app  ($APP_SIZE)"
echo "   Installer: dist/CarrotSummary.dmg  ($DMG_SIZE)"
echo ""
echo "   To test: open dist/CarrotSummary.app"
echo "   To distribute: share dist/CarrotSummary.dmg"
