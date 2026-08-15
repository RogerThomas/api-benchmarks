#!/usr/bin/env bash
# Launch an ASGI app under the configured Python server.
#   PYTHON_SERVER=granian (default) | uvicorn
#   WORKERS (default 1), LOOP (granian only; default uvloop)
# Usage: serve.sh <module:app> <host> <port>
# (ASGI only — Flask is WSGI and stays on granian; Robyn has its own server.)
set -euo pipefail
app="$1"
host="${2:-0.0.0.0}"
port="${3:-8000}"

case "${PYTHON_SERVER:-granian}" in
  granian)
    exec granian --interface asgi --loop "${LOOP:-uvloop}" \
      --host "$host" --port "$port" --workers "${WORKERS:-1}" "$app" ;;
  uvicorn)
    # uvloop + no per-request access log, to match granian's defaults.
    exec uvicorn --loop uvloop --no-access-log \
      --host "$host" --port "$port" --workers "${WORKERS:-1}" "$app" ;;
  *)
    echo "PYTHON_SERVER must be 'granian' or 'uvicorn' (got '${PYTHON_SERVER:-}')" >&2
    exit 2 ;;
esac
