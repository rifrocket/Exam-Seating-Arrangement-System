#!/usr/bin/env bash
# Shared helpers for scripts/{setup,start,stop,start-pm2}.sh. Sourced,
# never executed directly.
#
# Deliberately does not `source` (bash-eval) the project's .env files —
# some values (APP_CORS_ORIGINS, a JSON array; passwords with arbitrary
# characters) are not valid bash syntax once unquoted, and eval-ing an
# untrusted-shaped file is exactly the kind of thing that breaks in
# surprising ways. Every helper below reads one specific KEY= line with
# grep instead, which is safe regardless of what any other line contains.

ROOT_DIR="${EXAM_SEATING_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUN_DIR="$ROOT_DIR/.tmp"
mkdir -p "$RUN_DIR"

BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_LOG_FILE="$RUN_DIR/backend.log"
FRONTEND_LOG_FILE="$RUN_DIR/frontend.log"

# get_env_value <file> <KEY> <default>
# Prints the value of the last KEY=... line in <file>, or <default> if
# the file or key doesn't exist. Strips one layer of wrapping double
# quotes, if present. Never sources or evaluates the file.
get_env_value() {
  local file="$1" key="$2" default="$3"
  if [[ -f "$file" ]]; then
    local line
    line="$(grep -E "^${key}=" "$file" 2>/dev/null | tail -n1 || true)"
    if [[ -n "$line" ]]; then
      local value="${line#*=}"
      value="${value%\"}"
      value="${value#\"}"
      printf '%s' "$value"
      return 0
    fi
  fi
  printf '%s' "$default"
}

is_process_running() {
  local pid="${1:-}"
  [[ -n "$pid" && "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

# stop_pid_file <pid_file> <label>
# Stops the process recorded in <pid_file>, if any, and removes the
# file. Never touches any process this project didn't itself start and
# record here. Safe (no error) if nothing is running.
stop_pid_file() {
  local pid_file="$1" label="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "${label}: not running (no pid file)."
    return 0
  fi
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if ! is_process_running "$pid"; then
    echo "${label}: not running (removing stale pid file)."
    rm -f "$pid_file"
    return 0
  fi
  echo "Stopping ${label} (pid ${pid})..."
  kill "$pid" 2>/dev/null || true
  local waited=0
  while is_process_running "$pid" && [[ $waited -lt 5 ]]; do
    sleep 0.5
    waited=$((waited + 1))
  done
  if is_process_running "$pid"; then
    echo "${label} did not stop gracefully; sending SIGKILL to pid ${pid}."
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
  echo "${label} stopped."
}
