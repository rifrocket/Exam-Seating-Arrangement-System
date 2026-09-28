#!/usr/bin/env bash
# make start — starts (or cleanly restarts) both the backend (uvicorn,
# --reload) and frontend (next dev) as plain background processes,
# tracked by PID file under .tmp/. Simple local development process
# management — see scripts/start-pm2.sh for the PM2-managed alternative;
# the two are not meant to be used at the same time (see README).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

BACKEND_ENV="$ROOT_DIR/backend/.env"
FRONTEND_ENV="$ROOT_DIR/frontend/.env.local"

if [[ ! -f "$BACKEND_ENV" || ! -f "$FRONTEND_ENV" ]]; then
  echo "Missing environment configuration (backend/.env and/or frontend/.env.local)." >&2
  echo "Run 'make setup' first." >&2
  exit 1
fi

if [[ ! -x "$ROOT_DIR/backend/.venv/bin/uvicorn" ]]; then
  echo "backend/.venv not found (or has no uvicorn) — set up the backend virtual" >&2
  echo "environment first (see README's backend setup instructions)." >&2
  exit 1
fi

if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
  echo "frontend/node_modules not found — run 'npm install' in frontend/ first." >&2
  exit 1
fi

# Restart cleanly rather than launching duplicates: stop whatever this
# project previously started (if anything), before starting fresh.
stop_pid_file "$BACKEND_PID_FILE" "backend"
stop_pid_file "$FRONTEND_PID_FILE" "frontend"

BACKEND_HOST="$(get_env_value "$BACKEND_ENV" "BACKEND_HOST" "127.0.0.1")"
BACKEND_PORT="$(get_env_value "$BACKEND_ENV" "BACKEND_PORT" "8000")"
FRONTEND_HOST="$(get_env_value "$FRONTEND_ENV" "FRONTEND_HOST" "0.0.0.0")"
FRONTEND_PORT="$(get_env_value "$FRONTEND_ENV" "FRONTEND_PORT" "3000")"

echo "Starting backend on ${BACKEND_HOST}:${BACKEND_PORT} (log: .tmp/backend.log)..."
(
  cd "$ROOT_DIR/backend"
  nohup .venv/bin/uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload \
    > "$BACKEND_LOG_FILE" 2>&1 &
  echo $! > "$BACKEND_PID_FILE"
)

echo "Starting frontend on ${FRONTEND_HOST}:${FRONTEND_PORT} (log: .tmp/frontend.log)..."
(
  cd "$ROOT_DIR/frontend"
  nohup npx next dev -H "$FRONTEND_HOST" -p "$FRONTEND_PORT" \
    > "$FRONTEND_LOG_FILE" 2>&1 &
  echo $! > "$FRONTEND_PID_FILE"
)

sleep 1
echo
echo "Backend:  http://localhost:${BACKEND_PORT}  (pid $(cat "$BACKEND_PID_FILE"))"
echo "Frontend: http://localhost:${FRONTEND_PORT} (pid $(cat "$FRONTEND_PID_FILE"))"
echo
echo "Run 'make stop' to stop both. Logs are under .tmp/."
