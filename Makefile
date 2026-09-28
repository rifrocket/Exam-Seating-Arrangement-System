.PHONY: setup start stop start-pm2

# Interactive first-time (or re-)configuration: backend/.env and
# frontend/.env.local (ports, admin credentials, derived API URL/CORS).
setup:
	@bash scripts/setup.sh

# Simple local development: both services as plain background
# processes, tracked by PID file under .tmp/. Restarts cleanly if
# already running (never launches duplicates).
start:
	@bash scripts/start.sh

# Stops whatever `make start` started. Safe to run when nothing is
# running; never touches a process it didn't start itself.
stop:
	@bash scripts/stop.sh

# PM2-managed alternative to `make start`/`make stop` — see
# ecosystem.config.js. Requires PM2 to already be installed
# (npm install -g pm2); this target never installs it silently.
start-pm2:
	@bash scripts/start-pm2.sh
