#!/usr/bin/env bash
# make setup — provisions backend/.venv + frontend/node_modules if
# missing, then interactively configures backend/.env and
# frontend/.env.local: environment mode, backend port, frontend port,
# admin username, admin password, and the derived
# NEXT_PUBLIC_API_URL/APP_CORS_ORIGINS that let the two actually talk to
# each other. Never overwrites unrelated existing keys in either file.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_ENV="$BACKEND_DIR/.env"
FRONTEND_ENV="$FRONTEND_DIR/.env.local"
BACKEND_ENV_EXAMPLE="$BACKEND_DIR/.env.example"
FRONTEND_ENV_EXAMPLE="$FRONTEND_DIR/.env.example"

# set_kv <file> <KEY> <value>
# Replaces an existing KEY=... line in place, or appends one — every
# other line in the file is left untouched. Uses awk (not `sed -i`,
# whose in-place suffix argument differs between GNU and BSD/macOS sed)
# and passes the value through -v so special characters in it (quotes,
# brackets, `=`) are never re-parsed.
set_kv() {
  local file="$1" key="$2" value="$3"
  touch "$file"
  local tmp
  tmp="$(mktemp)"
  if grep -qE "^${key}=" "$file" 2>/dev/null; then
    awk -v k="$key" -v v="$value" 'BEGIN{FS=OFS="="} $1==k{print k"="v; next} {print}' "$file" > "$tmp"
  else
    cp "$file" "$tmp"
    printf '%s=%s\n' "$key" "$value" >> "$tmp"
  fi
  mv "$tmp" "$file"
}

has_key() {
  local file="$1" key="$2"
  [[ -f "$file" ]] && grep -qE "^${key}=" "$file" 2>/dev/null
}

is_valid_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && (( 10#$1 >= 1 && 10#$1 <= 65535 ))
}

echo "Exam Seating Arrangement System — setup"
echo "========================================"
echo

# --- 1. Provision dependencies (backend venv, frontend node_modules) ------
#
# A fresh clone has neither — `make start`/`make start-pm2` fail with a
# plain "not found" otherwise, on any machine that hasn't already set
# these up by hand.

echo "Checking backend virtual environment (backend/.venv)..."
if [[ ! -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  echo "Creating backend/.venv..."
  if command -v uv >/dev/null 2>&1; then
    (cd "$BACKEND_DIR" && uv venv .venv)
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m venv "$BACKEND_DIR/.venv"
  else
    echo "Neither 'uv' nor 'python3' was found on PATH — install Python 3.11+" >&2
    echo "(https://www.python.org/downloads/) or uv (https://docs.astral.sh/uv/)," >&2
    echo "then re-run 'make setup'." >&2
    exit 1
  fi
fi

echo "Installing backend dependencies..."
if command -v uv >/dev/null 2>&1; then
  # uv's own installer never needs a `pip` binary inside the venv at all
  # — preferred whenever uv is available, regardless of which tool
  # originally created backend/.venv (a `uv venv`-created one, in
  # particular, deliberately does not bundle pip).
  (cd "$BACKEND_DIR" && uv pip install --python .venv/bin/python -e ".[dev]" --quiet)
else
  # A venv created by `python3 -m venv` doesn't always bundle pip: some
  # Debian/Ubuntu systems need the OS's python3-venv package (with its
  # own ensurepip support) installed for that, and otherwise produce a
  # pip-less venv with no error at creation time. Checked and bootstrapped
  # functionally (`python -m pip`), not by looking for a `pip` file —
  # ensurepip itself doesn't always create a plain `pip` script (some
  # builds only produce versioned ones like `pip3`/`pip3.13`), so `python
  # -m pip` is used for every install below too, sidestepping the
  # question of which console-script name actually exists entirely.
  if ! "$BACKEND_DIR/.venv/bin/python" -m pip --version >/dev/null 2>&1; then
    echo "backend/.venv has no pip yet — bootstrapping it (ensurepip)..."
    if ! "$BACKEND_DIR/.venv/bin/python" -m ensurepip --upgrade >/dev/null 2>&1; then
      echo "Could not bootstrap pip inside backend/.venv (ensurepip unavailable)." >&2
      echo "On Debian/Ubuntu: sudo apt install python3-venv (matching your python3" >&2
      echo "version), then remove backend/.venv and re-run 'make setup'." >&2
      echo "Alternatively, install uv (https://docs.astral.sh/uv/), which does not" >&2
      echo "need pip in the venv at all." >&2
      exit 1
    fi
  fi
  "$BACKEND_DIR/.venv/bin/python" -m pip install --quiet --upgrade pip
  (cd "$BACKEND_DIR" && "$BACKEND_DIR/.venv/bin/python" -m pip install --quiet -e ".[dev]")
fi

echo "Checking frontend dependencies (frontend/node_modules)..."
if ! command -v npm >/dev/null 2>&1; then
  echo "npm was not found on PATH — install Node.js (https://nodejs.org/) first," >&2
  echo "then re-run 'make setup'." >&2
  exit 1
fi
(cd "$FRONTEND_DIR" && npm install --no-audit --no-fund --quiet)

echo "Dependencies ready."
echo

# --- 2. Interactive configuration -----------------------------------------

# Captured *before* the .env.example seeding below, specifically so the
# BACKEND_HOST default logic further down can tell "this key came from a
# real prior setup" apart from "this key is just .env.example's own
# placeholder default, copied in moments ago" — .env.example itself
# ships with a hardcoded BACKEND_HOST=127.0.0.1 line, which would
# otherwise make every fresh setup look "already configured."
backend_env_pre_existed=false
[[ -f "$BACKEND_ENV" ]] && backend_env_pre_existed=true

# Seed each env file from its own .env.example the first time, so
# unrelated defaults (APP_DATABASE_URL, AUTH_SECRET placeholder, ...)
# already exist and this script only has to manage the values it's
# actually responsible for. An already-existing file is never replaced
# wholesale.
if [[ ! -f "$BACKEND_ENV" && -f "$BACKEND_ENV_EXAMPLE" ]]; then
  cp "$BACKEND_ENV_EXAMPLE" "$BACKEND_ENV"
fi
if [[ ! -f "$FRONTEND_ENV" && -f "$FRONTEND_ENV_EXAMPLE" ]]; then
  cp "$FRONTEND_ENV_EXAMPLE" "$FRONTEND_ENV"
fi

default_environment="$(get_env_value "$BACKEND_ENV" "APP_ENVIRONMENT" "development")"
while true; do
  read -r -p "Environment (development/production) [$default_environment]: " app_environment
  app_environment="${app_environment:-$default_environment}"
  app_environment="$(printf '%s' "$app_environment" | tr '[:upper:]' '[:lower:]')"
  case "$app_environment" in
    development | production) break ;;
    *) echo "Please enter 'development' or 'production'." ;;
  esac
done

default_backend_port="$(get_env_value "$BACKEND_ENV" "BACKEND_PORT" "8000")"
default_frontend_port="$(get_env_value "$FRONTEND_ENV" "FRONTEND_PORT" "3000")"
default_admin_username="$(get_env_value "$BACKEND_ENV" "APP_ADMIN_USERNAME" "admin")"

# BACKEND_HOST's sensible default depends on the chosen environment —
# loopback-only is the safer default for local development, but a real
# production deployment (e.g. an actual server/VM) needs to bind every
# interface to be reachable at all. Only applied on a genuinely first-time
# setup (backend/.env didn't exist before this run) — a value already
# present from an *earlier* setup is always preserved, never silently
# changed out from under a re-run. `backend_env_pre_existed` (not
# `has_key` here) is what makes this distinction correctly: by this point
# BACKEND_HOST *always* has a value (from .env.example's own seeded
# placeholder, if nothing else), so checking key-presence alone could
# never tell a real prior setup apart from a brand-new file.
if [[ "$backend_env_pre_existed" == "true" ]] && has_key "$BACKEND_ENV" "BACKEND_HOST"; then
  default_backend_host="$(get_env_value "$BACKEND_ENV" "BACKEND_HOST" "127.0.0.1")"
elif [[ "$app_environment" == "production" ]]; then
  default_backend_host="0.0.0.0"
else
  default_backend_host="127.0.0.1"
fi
default_frontend_host="$(get_env_value "$FRONTEND_ENV" "FRONTEND_HOST" "0.0.0.0")"

while true; do
  read -r -p "Backend port [$default_backend_port]: " backend_port
  backend_port="${backend_port:-$default_backend_port}"
  if is_valid_port "$backend_port"; then
    break
  fi
  echo "Please enter a valid TCP port (1-65535)."
done

while true; do
  read -r -p "Frontend port [$default_frontend_port]: " frontend_port
  frontend_port="${frontend_port:-$default_frontend_port}"
  if ! is_valid_port "$frontend_port"; then
    echo "Please enter a valid TCP port (1-65535)."
    continue
  fi
  if [[ "$frontend_port" == "$backend_port" ]]; then
    echo "Frontend port must be different from the backend port ($backend_port)."
    continue
  fi
  break
done

read -r -p "Admin username [$default_admin_username]: " admin_username
admin_username="${admin_username:-$default_admin_username}"

while true; do
  read -r -s -p "Admin password: " admin_password
  echo
  if [[ -z "$admin_password" ]]; then
    echo "Password cannot be empty."
    continue
  fi
  read -r -s -p "Confirm admin password: " admin_password_confirm
  echo
  if [[ "$admin_password" != "$admin_password_confirm" ]]; then
    echo "Passwords did not match. Please try again."
    continue
  fi
  break
done

# Browser-facing, not the bind address: 0.0.0.0/:: is valid for
# BACKEND_HOST/FRONTEND_HOST (bind-all), but a browser can never open a
# connection *to* 0.0.0.0 — so the values the two apps use to reach each
# other (and the CORS origins the backend accepts) are always
# localhost/127.0.0.1 at the chosen port, regardless of bind host.
api_url="http://localhost:${backend_port}"
cors_origins="[\"http://localhost:${frontend_port}\", \"http://127.0.0.1:${frontend_port}\"]"

set_kv "$BACKEND_ENV" "APP_ENVIRONMENT" "$app_environment"
set_kv "$BACKEND_ENV" "BACKEND_HOST" "$default_backend_host"
set_kv "$BACKEND_ENV" "BACKEND_PORT" "$backend_port"
set_kv "$BACKEND_ENV" "APP_ADMIN_USERNAME" "$admin_username"
set_kv "$BACKEND_ENV" "APP_ADMIN_PASSWORD" "$admin_password"
set_kv "$BACKEND_ENV" "APP_CORS_ORIGINS" "$cors_origins"

set_kv "$FRONTEND_ENV" "FRONTEND_HOST" "$default_frontend_host"
set_kv "$FRONTEND_ENV" "FRONTEND_PORT" "$frontend_port"
set_kv "$FRONTEND_ENV" "NEXT_PUBLIC_API_URL" "$api_url"
set_kv "$FRONTEND_ENV" "ADMIN_USERNAME" "$admin_username"
set_kv "$FRONTEND_ENV" "ADMIN_PASSWORD" "$admin_password"

# AUTH_SECRET signs session cookies — never overwrite one that already
# exists (that would silently log out every current session), and never
# print it.
existing_auth_secret="$(get_env_value "$FRONTEND_ENV" "AUTH_SECRET" "")"
if [[ -z "$existing_auth_secret" || "$existing_auth_secret" == "change-me-too" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    auth_secret="$(openssl rand -base64 32)"
  else
    auth_secret="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 44)"
  fi
  set_kv "$FRONTEND_ENV" "AUTH_SECRET" "$auth_secret"
fi

unset admin_password admin_password_confirm

echo
echo "Configuration written (environment: $app_environment):"
echo "  backend/.env         (APP_ENVIRONMENT, BACKEND_HOST, BACKEND_PORT, APP_ADMIN_USERNAME, APP_ADMIN_PASSWORD, APP_CORS_ORIGINS)"
echo "  frontend/.env.local  (FRONTEND_HOST, FRONTEND_PORT, NEXT_PUBLIC_API_URL, ADMIN_USERNAME, ADMIN_PASSWORD)"
echo
echo "Neither file is committed to git (see .gitignore)."
echo "Run 'make start' (or 'make start-pm2') to launch both services."
