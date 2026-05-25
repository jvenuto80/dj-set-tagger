#!/bin/bash
# Build script for SetList native macOS app
# Bundles: Tauri shell + React frontend + Python backend
#
# Uses a local temp directory for the Vite build to avoid slow
# cloud-storage I/O (SeaDrive, iCloud, Dropbox, etc.)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
BACKEND_DIR="$PROJECT_ROOT/backend"
TAURI_DIR="$FRONTEND_DIR/src-tauri"
RESOURCES_DIR="$TAURI_DIR/resources"
TMPBUILD="/tmp/setlist-build-$$"
OUTPUT_DIR="${1:-$HOME/Desktop}"

echo "=== SetList Build ==="
echo "Project root: $PROJECT_ROOT"

# 1. Ensure Rust is available
if ! command -v cargo &> /dev/null; then
    echo "Error: Rust/Cargo not found. Install via: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    exit 1
fi

# 2. Build frontend on local disk (much faster than cloud storage)
echo ""
echo "--- Building frontend (local disk) ---"
rm -rf "$TMPBUILD"
mkdir -p "$TMPBUILD/frontend"
rsync -a --exclude node_modules --exclude dist --exclude .vite \
    "$FRONTEND_DIR/" "$TMPBUILD/frontend/"
cd "$TMPBUILD/frontend"
npm install --prefer-offline 2>&1 | tail -3
npx vite build 2>&1
echo "Frontend built successfully"
# Copy dist back
rm -rf "$FRONTEND_DIR/dist"
cp -r "$TMPBUILD/frontend/dist" "$FRONTEND_DIR/dist"
rm -rf "$TMPBUILD"

# 3. Copy Python backend into Tauri resources (bundled with the app)
echo ""
echo "--- Bundling Python backend ---"
rm -rf "$RESOURCES_DIR"
mkdir -p "$RESOURCES_DIR"

# Copy backend source
cp -r "$BACKEND_DIR" "$RESOURCES_DIR/backend"

# Copy run.py and requirements.txt
cp "$PROJECT_ROOT/run.py" "$RESOURCES_DIR/run.py"
cp "$BACKEND_DIR/requirements.txt" "$RESOURCES_DIR/requirements.txt"

echo "Backend bundled to $RESOURCES_DIR"

# 4. Build the Tauri app
echo ""
echo "--- Building Tauri app (this takes a few minutes on first build) ---"
cd "$FRONTEND_DIR"
npm run tauri:build

echo ""
echo "=== Build complete ==="

# 5. Copy final artifacts to output directory
APP_BUNDLE="$TAURI_DIR/target/release/bundle/macos/SetList.app"
DMG_FILE=$(find "$TAURI_DIR/target/release/bundle/dmg/" -name "*.dmg" 2>/dev/null | head -1)

if [ -d "$APP_BUNDLE" ]; then
    echo ""
    echo "--- Copying to $OUTPUT_DIR ---"
    # Remove any prior bundle so the new one fully replaces it
    # (plain `cp -r` over an existing .app silently merges and preserves stale files)
    rm -rf "$OUTPUT_DIR/SetList.app"
    cp -R "$APP_BUNDLE" "$OUTPUT_DIR/SetList.app"
    echo "✅ SetList.app → $OUTPUT_DIR/SetList.app"
fi

if [ -n "$DMG_FILE" ]; then
    cp "$DMG_FILE" "$OUTPUT_DIR/"
    echo "✅ DMG → $OUTPUT_DIR/$(basename "$DMG_FILE")"
fi

echo ""
echo "To run: open \"$OUTPUT_DIR/SetList.app\""
echo "To distribute: share the .dmg file"
