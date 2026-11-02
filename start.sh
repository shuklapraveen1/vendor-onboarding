#!/usr/bin/env bash
# One-command start for macOS/Linux; the same launcher start.bat uses on Windows.
# Sets up Python deps (first run only), generates demo documents, builds the UI if
# frontend/dist is missing and serves everything on http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"
exec python3 run.py "$@"
