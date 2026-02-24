#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$ROOT/.reports/hosted-local/hosted-local.log"

show_port() {
  local port="$1"
  local label="$2"
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "$label: UP ($port)"
    lsof -nP -iTCP:"$port" -sTCP:LISTEN
  else
    echo "$label: DOWN ($port)"
  fi
}

show_port 8787 "Backend"
echo "---"
show_port 3000 "Frontend"
echo "---"
if [[ -f "$LOG_FILE" ]]; then
  tail -n 30 "$LOG_FILE"
else
  echo "No hosted-local log file yet."
fi
