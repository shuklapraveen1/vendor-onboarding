#!/usr/bin/env bash
# Development mode: API with auto-reload on :8000 and Vite with HMR on :5173.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

cd "$ROOT/backend"
[ -f sample_data/scenarios.json ] || .venv/bin/python -m scripts.generate_samples
VO_PUBLIC_BASE_URL=http://localhost:5173 .venv/bin/uvicorn app.main:app --reload --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

cd "$ROOT/frontend"
npm run dev
