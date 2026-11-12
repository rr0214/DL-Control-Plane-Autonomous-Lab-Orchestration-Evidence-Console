#!/usr/bin/env bash
# One command to run the SDL Control Plane: FastAPI on :8000 and Next.js on :3000.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
command -v npm >/dev/null || { echo "npm is required (install Node.js 18 or newer)"; exit 1; }

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add ANTHROPIC_API_KEY to enable real LLM planning."
fi

if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
fi
backend/.venv/bin/pip install -q -r backend/requirements.txt

(cd frontend && npm install --no-audit --no-fund)

cleanup() {
  trap - EXIT INT TERM
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(cd "$ROOT/backend" && "$ROOT/backend/.venv/bin/uvicorn" app.api:app --port 8000) &
(cd "$ROOT/frontend" && npm run dev -- --port 3000) &

echo ""
echo "API:      http://localhost:8000/docs"
echo "Console:  http://localhost:3000"
echo "Press Ctrl+C to stop both servers."
wait
