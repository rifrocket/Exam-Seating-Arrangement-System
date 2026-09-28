// PM2 process definitions for `make start-pm2` (scripts/start-pm2.sh).
//
// Reads BACKEND_HOST/BACKEND_PORT/FRONTEND_HOST/FRONTEND_PORT from the
// current shell environment — scripts/start-pm2.sh exports them (read
// from backend/.env / frontend/.env.local) before invoking `pm2
// startOrReload` on this file. Running `pm2 start ecosystem.config.js`
// directly (bypassing the script) falls back to this project's own
// established defaults below.
//
// No --reload here (unlike scripts/start.sh's dev-mode uvicorn): PM2
// itself supervises and restarts these processes on crash, and mixing
// uvicorn's own file-watching reloader with PM2's process ownership
// would fight over which process is "the" tracked one.
//
// Both apps' `env` blocks unconditionally force a production environment
// — not `env_production` (PM2's opt-in-via-`--env production` variant),
// since `make start-pm2` must always run production-mode regardless of
// what backend/.env's own APP_ENVIRONMENT happens to say, or whether the
// operator remembers to pass a flag. A real environment variable set
// here always overrides whatever `backend/.env` itself contains
// (pydantic-settings treats the process environment as taking priority
// over its `env_file`), so this is a genuine guarantee, not just a
// default.
const BACKEND_HOST = process.env.BACKEND_HOST || "127.0.0.1";
const BACKEND_PORT = process.env.BACKEND_PORT || "8000";
const FRONTEND_HOST = process.env.FRONTEND_HOST || "0.0.0.0";
const FRONTEND_PORT = process.env.FRONTEND_PORT || "3000";

module.exports = {
  apps: [
    {
      name: "exam-seating-backend",
      cwd: "./backend",
      script: ".venv/bin/uvicorn",
      // Not a Node script — run its own shebang directly rather than
      // having PM2 try to execute it via `node`.
      interpreter: "none",
      args: `app.main:app --host ${BACKEND_HOST} --port ${BACKEND_PORT}`,
      env: {
        APP_ENVIRONMENT: "production",
      },
    },
    {
      name: "exam-seating-frontend",
      cwd: "./frontend",
      script: "node_modules/.bin/next",
      args: `start -H ${FRONTEND_HOST} -p ${FRONTEND_PORT}`,
      env: {
        NODE_ENV: "production",
      },
    },
  ],
};
