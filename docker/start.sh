#!/bin/bash

# Start the FastAPI backend
cd /app
python -m uvicorn backend.main:app --host 0.0.0.0 --port 5000 &

# Start a simple static file server for the frontend
cd /app/frontend/dist
python -m http.server 8080 &

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?
