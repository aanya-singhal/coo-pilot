#!/usr/bin/env bash
# One command to get demo-ready: backend, console server, warm cache.
#
#   ./scripts/start_demo.sh
#
# Safe to re-run - it restarts whatever is already going. Takes ~60s the first
# time because the extraction cache has to be warmed; after that it is quick.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"
LOG_DIR="${TMPDIR:-/tmp}/coo-pilot"
mkdir -p "$LOG_DIR"

echo "stopping anything already running..."
pkill -f "uvicorn backend.main:app" 2>/dev/null || true
pkill -f "http.server 5500" 2>/dev/null || true
sleep 1

if [ ! -f .env ] || ! grep -qE '^GEMINI_API_KEY=.+' .env; then
  echo
  echo "  WARNING: GEMINI_API_KEY is not set in .env"
  echo "  Extraction will fail and the console will show recorded data."
  echo
fi

echo "starting backend on :8000 ..."
nohup "$PY" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 \
  > "$LOG_DIR/backend.log" 2>&1 &

echo "starting console on :5500 ..."
nohup "$PY" -m http.server 5500 --bind 127.0.0.1 \
  > "$LOG_DIR/static.log" 2>&1 &

printf "waiting for backend "
for _ in $(seq 1 40); do
  if curl -sf --max-time 2 http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo " up"; break
  fi
  printf "."; sleep 1
done

if ! curl -sf --max-time 2 http://127.0.0.1:8000/health > /dev/null 2>&1; then
  echo
  echo "backend did not start. Last lines of $LOG_DIR/backend.log:" >&2
  tail -20 "$LOG_DIR/backend.log" >&2
  exit 1
fi

echo
echo "warming the extraction cache (this is the slow part, ~45s)..."
./scripts/warm_cache.sh || echo "  (warm-up had trouble - the demo still works, first click will be slow)"

echo
echo "════════════════════════════════════════════════"
echo "  READY"
echo
echo "  Console   http://127.0.0.1:5500/console.html"
echo "  API docs  http://127.0.0.1:8000/docs"
echo
echo "  Script    docs/DEMO.md"
echo "  Logs      $LOG_DIR/backend.log"
echo "════════════════════════════════════════════════"
