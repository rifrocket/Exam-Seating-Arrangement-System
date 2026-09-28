#!/usr/bin/env bash
# make start-pm2 — starts (or reloads) both processes under PM2, using
# ecosystem.config.js. This is the PM2-managed alternative to
# scripts/start.sh; the two are not meant to be run at the same time
# (see README) — PM2 owns whatever it starts here, with its own restart
# behavior, not the .tmp/*.pid files scripts/start.sh uses.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

if ! command -v pm2 >/dev/null 2>&1; then
  echo "PM2 is not installed (or not on PATH)." >&2
  echo >&2
  echo "Install it with:" >&2
  echo "    npm install -g pm2" >&2
  echo >&2
  echo "Then re-run: make start-pm2" >&2
  exit 1
fi

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

# `next start` (what PM2 runs, below) serves a production build, not
# live source — unlike scripts/start.sh's `next dev`, PM2 needs one to
# already exist. Building here, every time, is the explicit, simple
# choice over silently serving a stale .next/ from an earlier run.
echo "Building frontend for production (required for 'next start' under PM2)..."
(cd "$ROOT_DIR/frontend" && npm run build)

export BACKEND_HOST="$(get_env_value "$BACKEND_ENV" "BACKEND_HOST" "127.0.0.1")"
export BACKEND_PORT="$(get_env_value "$BACKEND_ENV" "BACKEND_PORT" "8000")"
export FRONTEND_HOST="$(get_env_value "$FRONTEND_ENV" "FRONTEND_HOST" "0.0.0.0")"
export FRONTEND_PORT="$(get_env_value "$FRONTEND_ENV" "FRONTEND_PORT" "3000")"

# ecosystem.config.js unconditionally sets APP_ENVIRONMENT=production
# (backend) and NODE_ENV=production (frontend) in each app's own `env`
# block — this always wins over backend/.env's own APP_ENVIRONMENT, so
# PM2-managed processes run in production mode regardless of that file's
# contents or whether this script is bypassed in favor of `pm2 start
# ecosystem.config.js` directly.
echo "Starting under a forced production environment (APP_ENVIRONMENT=production, NODE_ENV=production)..."
pm2 startOrReload "$ROOT_DIR/ecosystem.config.js"
pm2 save

echo
echo "PM2-managed processes:"
pm2 list
