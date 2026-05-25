#!/bin/bash
# Development script: runs Python backend + Tauri dev mode
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo "=== SetList Dev Mode ==="

# Check for Python venv
VENV="$PROJECT_ROOT/.venv-setlist"
if [ -d "$VENV" ]; then
    echo "Activating venv: $VENV"
    source "$VENV/bin/activate"
fi

# Start Python backend in background (loopback only — matches production port)
echo "Starting Python backend on 127.0.0.1:5050..."
cd "$PROJECT_ROOT"
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 5050 --reload &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Wait for backend to be ready
echo "Waiting for backend..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:5050/api/health > /dev/null 2>&1; then
        echo "Backend ready!"
        break
    fi
    sleep 1
done

# Start Tauri dev (which starts Vite + opens native window)
echo "Starting Tauri dev mode..."
cd "$FRONTEND_DIR"
npm run tauri:dev

# Cleanup: kill backend when Tauri exits
echo "Shutting down backend..."
kill $BACKEND_PID 2>/dev/null || true
wait $BACKEND_PID 2>/dev/null || true
echo "Done."
