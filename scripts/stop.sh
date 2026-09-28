#!/usr/bin/env bash
# make stop — stops whatever backend/frontend processes scripts/start.sh
# recorded PIDs for. Never uses a broad pkill/killall; only ever signals
# the exact tracked PIDs, and never errors just because nothing is running.
set -uo pipefail  # deliberately no -e: stopping must be forgiving/idempotent
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

stop_pid_file "$BACKEND_PID_FILE" "backend"
stop_pid_file "$FRONTEND_PID_FILE" "frontend"
