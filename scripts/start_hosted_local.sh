#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="$ROOT/proof_of_concept_ui/frontend"
LOG_DIR="$ROOT/.reports/hosted-local"
LOG_FILE="$LOG_DIR/hosted-local.log"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"

mkdir -p "$LOG_DIR"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >>"$LOG_FILE"
}

port_in_use() {
  /usr/bin/python3 - "$1" <<'PY'
import socket, sys
port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(0.4)
code = s.connect_ex(("127.0.0.1", port))
s.close()
sys.exit(0 if code == 0 else 1)
PY
}

ensure_backend_env() {
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    return 0
  fi
  log "Creating backend virtualenv..."
  /usr/bin/python3 -m venv "$ROOT/.venv" >>"$LOG_FILE" 2>&1
  "$ROOT/.venv/bin/python" -m pip install -U pip >>"$LOG_FILE" 2>&1
  "$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements-web.txt" >>"$LOG_FILE" 2>&1
}

ensure_frontend_env() {
  if [[ ! -d "$FRONTEND/node_modules" ]]; then
    log "Installing frontend dependencies..."
    (cd "$FRONTEND" && npm install) >>"$LOG_FILE" 2>&1
  fi
  if [[ ! -d "$FRONTEND/.next" ]]; then
    log "Building frontend..."
    (cd "$FRONTEND" && npm run build) >>"$LOG_FILE" 2>&1
  fi
}

start_backend() {
  if port_in_use 8787; then
    log "Backend already listening on 8787."
    return 0
  fi
  log "Starting backend (8787)..."
  (
    cd "$ROOT"
    nohup "$ROOT/.venv/bin/python" "$ROOT/run_web.py" >>"$LOG_FILE" 2>&1 &
    echo $! >"$BACKEND_PID_FILE"
  )
}

start_frontend() {
  if port_in_use 3000; then
    log "Frontend already listening on 3000."
    return 0
  fi
  log "Starting frontend (3000)..."
  (
    cd "$FRONTEND"
    export PLUGGY_API_BASE_URL="http://127.0.0.1:8787"
    # next.config sets output=standalone, so "next start" is not valid here.
    export PORT=3000
    nohup node .next/standalone/server.js >>"$LOG_FILE" 2>&1 &
    echo $! >"$FRONTEND_PID_FILE"
  )
}

ensure_backend_env
ensure_frontend_env
start_backend
start_frontend

sleep 2
/usr/bin/open "http://localhost:3000" >/dev/null 2>&1 || true
echo "Hosted-local mode started: http://localhost:3000"
echo "Logs: $LOG_FILE"
