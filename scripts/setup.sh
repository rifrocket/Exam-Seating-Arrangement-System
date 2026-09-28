#!/usr/bin/env bash
# make setup — interactively configures backend/.env and
# frontend/.env.local: backend port, frontend port, admin username,
# admin password, and the derived NEXT_PUBLIC_API_URL/APP_CORS_ORIGINS
# that let the two actually talk to each other. Never overwrites unrelated
# existing keys in either file.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

BACKEND_ENV="$ROOT_DIR/backend/.env"
FRONTEND_ENV="$ROOT_DIR/frontend/.env.local"
BACKEND_ENV_EXAMPLE="$ROOT_DIR/backend/.env.example"
FRONTEND_ENV_EXAMPLE="$ROOT_DIR/frontend/.env.example"

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

is_valid_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && (( 10#$1 >= 1 && 10#$1 <= 65535 ))
}

echo "Exam Seating Arrangement System — setup"
echo "========================================"
echo "Configuring backend/.env and frontend/.env.local."
echo

# Seed each file from its own .env.example the first time, so unrelated
# defaults (APP_DATABASE_URL, AUTH_SECRET placeholder, ...) already exist
# and this script only has to manage the values it's actually responsible
# for. An already-existing file is never replaced wholesale.
if [[ ! -f "$BACKEND_ENV" && -f "$BACKEND_ENV_EXAMPLE" ]]; then
  cp "$BACKEND_ENV_EXAMPLE" "$BACKEND_ENV"
fi
if [[ ! -f "$FRONTEND_ENV" && -f "$FRONTEND_ENV_EXAMPLE" ]]; then
  cp "$FRONTEND_ENV_EXAMPLE" "$FRONTEND_ENV"
fi

default_backend_port="$(get_env_value "$BACKEND_ENV" "BACKEND_PORT" "8000")"
default_frontend_port="$(get_env_value "$FRONTEND_ENV" "FRONTEND_PORT" "3000")"
default_admin_username="$(get_env_value "$BACKEND_ENV" "APP_ADMIN_USERNAME" "admin")"
default_backend_host="$(get_env_value "$BACKEND_ENV" "BACKEND_HOST" "127.0.0.1")"
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
echo "Configuration written:"
echo "  backend/.env         (BACKEND_HOST, BACKEND_PORT, APP_ADMIN_USERNAME, APP_ADMIN_PASSWORD, APP_CORS_ORIGINS)"
echo "  frontend/.env.local  (FRONTEND_HOST, FRONTEND_PORT, NEXT_PUBLIC_API_URL, ADMIN_USERNAME, ADMIN_PASSWORD)"
echo
echo "Neither file is committed to git (see .gitignore)."
echo "Run 'make start' (or 'make start-pm2') to launch both services."
