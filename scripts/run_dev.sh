#!/usr/bin/env sh
set -eu
python -m app.worker &
worker_pid=$!
trap 'kill "$worker_pid" 2>/dev/null || true' EXIT INT TERM
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port "${PORT:-8000}" --workers 1 --no-access-log
