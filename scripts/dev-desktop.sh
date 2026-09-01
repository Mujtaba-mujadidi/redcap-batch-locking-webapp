#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
DESKTOP_DATA_DIR="${APP_DATA_DIR:-$ROOT_DIR/.desktop-dev-data}"
DESKTOP_EXPIRY_DATE="${APP_EXPIRY_DATE:-2027-02-28}"

export APP_MODE=desktop
export APP_DATA_DIR="$DESKTOP_DATA_DIR"
export APP_EXPIRY_DATE="$DESKTOP_EXPIRY_DATE"
export DESKTOP_API_HOST=127.0.0.1
export DESKTOP_API_PORT=8765
export REDCAP_API_KEY_CACHE_SECRET=desktop-local-redcap-api-key-cache-secret
export REDCAP_SSL_VERIFY=false
export NEXT_PUBLIC_APP_MODE=desktop
export NEXT_PUBLIC_BACKEND_ORIGIN="http://${DESKTOP_API_HOST}:${DESKTOP_API_PORT}"

DESKTOP_UI_PORT="${DESKTOP_UI_PORT:-3847}"

mkdir -p "$DESKTOP_DATA_DIR"

echo "Desktop data directory: $DESKTOP_DATA_DIR"
echo "Backend API: http://${DESKTOP_API_HOST}:${DESKTOP_API_PORT}"
echo "Frontend UI: http://localhost:${DESKTOP_UI_PORT}"
echo
echo "Press Ctrl+C to stop both services."

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

(
  cd "$BACKEND_DIR"
  if [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
  fi
  python scripts/run_desktop.py
) &
BACKEND_PID=$!

sleep 2

cd "$FRONTEND_DIR"
npm run dev:desktop -- --port "$DESKTOP_UI_PORT"
