#!/usr/bin/env bash
# One command to run the SDL Control Plane:
#   Arize Phoenix on :6006, FastAPI on :8000, Next.js on :3000.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
command -v npm >/dev/null || { echo "npm is required (install Node.js 18 or newer)"; exit 1; }

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add ANTHROPIC_API_KEY to enable real LLM planning."
fi

# Install Python deps. uv is much faster than pip (Phoenix is a large install); use it when present.
if [ ! -d backend/.venv ]; then
  if command -v uv >/dev/null; then uv venv -q backend/.venv; else python3 -m venv backend/.venv; fi
fi
if command -v uv >/dev/null; then
  uv pip install -q --python backend/.venv/bin/python -r backend/requirements.txt
else
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi

(cd frontend && npm install --no-audit --no-fund)

cleanup() {
  trap - EXIT INT TERM
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

PY="$ROOT/backend/.venv/bin/python"
export PHOENIX_PORT=6006
export PHOENIX_COLLECTOR_ENDPOINT="http://localhost:6006"
export PHOENIX_WORKING_DIR="$ROOT/backend/data/phoenix"
mkdir -p "$PHOENIX_WORKING_DIR"

# 1) Phoenix first, so the API can register tracing when it starts.
"$ROOT/backend/.venv/bin/phoenix" serve > "$PHOENIX_WORKING_DIR/phoenix.log" 2>&1 &
echo -n "Waiting for Phoenix on :6006 "
PHOENIX_UP=0
for _ in $(seq 1 90); do
  if "$PY" -c "import urllib.request; urllib.request.urlopen('http://localhost:6006', timeout=1)" 2>/dev/null; then
    PHOENIX_UP=1; break
  fi
  echo -n "."; sleep 1
done
echo ""

# 2) Seed the curated error-analysis traces and the golden dataset (safe to re-run).
if [ "$PHOENIX_UP" = "1" ]; then
  (cd "$ROOT/backend" && "$PY" -m app.seed_phoenix) || echo "Phoenix seeding skipped."
else
  echo "Phoenix did not start (see backend/data/phoenix/phoenix.log). Continuing without tracing."
fi

# 3) API and web app.
(cd "$ROOT/backend" && "$ROOT/backend/.venv/bin/uvicorn" app.api:app --port 8000) &
(cd "$ROOT/frontend" && npm run dev -- --port 3000) &

echo ""
echo "Console:  http://localhost:3000"
echo "API docs: http://localhost:8000/docs"
echo "Phoenix:  http://localhost:6006   (live runs: sdl-control-plane, curated examples: sdl-control-plane-seed)"
echo "Press Ctrl+C to stop everything."
wait
