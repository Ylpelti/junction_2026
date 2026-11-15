#!/bin/sh
set -eu
if [ "$#" -gt 0 ]; then
    exec "$@"
fi
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --timeout-graceful-shutdown 30 --no-access-log
