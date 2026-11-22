#!/usr/bin/env sh
set -eu
export PATHYA_ENV=prod
export AUTH_MODE=session
python -m app.worker &
worker_pid=$!
trap 'kill "$worker_pid" 2>/dev/null || true' EXIT INT TERM
# Terminate HTTPS at an explicitly configured trusted reverse proxy.
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port "${PORT:-8000}" --workers 1 --no-access-log
