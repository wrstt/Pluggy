#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${PLATSWAP_ROOT:-$SCRIPT_DIR}"
LOG_DIR=""
LOG_FILE=""
BACKEND_PID_FILE=""
FRONTEND_PID_FILE=""
LOCK_DIR="/tmp/platswap-studio-launch.lock"
THROTTLE_FILE="/tmp/platswap-studio-launch.last"
SPLASH_FILE=""

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

notify() {
  local msg="$1"
  /usr/bin/osascript -e "display notification \"$msg\" with title \"Pluggy\"" >/dev/null 2>&1 || true
}

alert() {
  local msg="$1"
  /usr/bin/osascript -e "display alert \"Pluggy\" message \"$msg\"" >/dev/null 2>&1 || true
}

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >>"$LOG_FILE"
}

resolve_npm() {
  if command -v npm >/dev/null 2>&1; then
    command -v npm
    return 0
  fi
  for candidate in /opt/homebrew/bin/npm /usr/local/bin/npm; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  for profile in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.profile" "$HOME/.bash_profile"; do
    if [[ -f "$profile" ]]; then
      # shellcheck disable=SC1090
      source "$profile" >/dev/null 2>&1 || true
    fi
  done
  if command -v npm >/dev/null 2>&1; then
    command -v npm
    return 0
  fi
  return 1
}

if [[ ! -f "$ROOT/run_web.py" ]]; then
  for candidate in "$SCRIPT_DIR/.." "$SCRIPT_DIR/../.." "$SCRIPT_DIR/../../.."; do
    if [[ -f "$candidate/run_web.py" ]]; then
      ROOT="$(cd "$candidate" && pwd)"
      break
    fi
  done
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  exit 0
fi
cleanup_lock() {
  rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
}
trap cleanup_lock EXIT

now_epoch="$(date +%s)"
last_epoch="0"
if [[ -f "$THROTTLE_FILE" ]]; then
  last_epoch="$(cat "$THROTTLE_FILE" 2>/dev/null || echo 0)"
fi
if [[ "$last_epoch" =~ ^[0-9]+$ ]] && (( now_epoch - last_epoch < 12 )); then
  exit 0
fi
printf '%s\n' "$now_epoch" >"$THROTTLE_FILE"

NPM_BIN="$(resolve_npm || true)"
if [[ -z "${NPM_BIN:-}" ]]; then
  LOG_DIR="$ROOT/.reports/launcher"
  LOG_FILE="$LOG_DIR/launch.log"
  mkdir -p "$LOG_DIR"
  log "Unable to find npm in PATH. Install Node.js or set PATH for GUI apps."
  notify "Launch failed: npm not found"
  alert "Launch failed: npm not found. Install Node.js or start once from Terminal."
  exit 1
fi

LOG_DIR="$ROOT/.reports/launcher"
LOG_FILE="$LOG_DIR/launch.log"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"
mkdir -p "$LOG_DIR"

log "Using npm at: $NPM_BIN"

if [[ ! -f "$ROOT/run_web.py" ]]; then
  log "Unable to locate run_web.py. Set PLATSWAP_ROOT and retry."
  notify "Launch failed: project root not found"
  alert "Launch failed: project root not found."
  exit 1
fi

port_in_use() {
  /usr/bin/python3 - "$1" <<'PY'
import socket, sys
port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(0.5)
code = s.connect_ex(("127.0.0.1", port))
s.close()
sys.exit(0 if code == 0 else 1)
PY
}

ensure_venv() {
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    return 0
  fi
  notify "First run setup: creating Python environment"
  log "Creating virtualenv..."
  /usr/bin/python3 -m venv "$ROOT/.venv" >>"$LOG_FILE" 2>&1
  "$ROOT/.venv/bin/python" -m pip install -U pip >>"$LOG_FILE" 2>&1
  "$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements-web.txt" >>"$LOG_FILE" 2>&1
}

frontend_needs_build() {
  local frontend="$1"
  local build_id="$frontend/.next/BUILD_ID"
  if [[ ! -f "$build_id" ]]; then
    return 0
  fi
  local watched=(
    "$frontend/app"
    "$frontend/components"
    "$frontend/lib"
    "$frontend/public"
    "$frontend/next.config.js"
    "$frontend/next.config.mjs"
    "$frontend/next.config.ts"
    "$frontend/postcss.config.js"
    "$frontend/tailwind.config.js"
    "$frontend/tailwind.config.ts"
    "$frontend/package.json"
    "$frontend/package-lock.json"
    "$frontend/tsconfig.json"
  )
  local path
  for path in "${watched[@]}"; do
    if [[ -e "$path" ]] && /usr/bin/find "$path" -type f -newer "$build_id" | /usr/bin/head -n 1 | /usr/bin/grep -q .; then
      return 0
    fi
  done
  return 1
}

ensure_frontend() {
  local frontend="$ROOT/proof_of_concept_ui/frontend"
  if [[ ! -d "$frontend" ]]; then
    log "Missing frontend directory: $frontend"
    notify "Launch failed: frontend folder missing"
    alert "Launch failed: frontend folder missing."
    exit 1
  fi
  if [[ ! -d "$frontend/node_modules" ]]; then
    notify "First run setup: installing frontend packages"
    log "Running npm install..."
    (cd "$frontend" && "$NPM_BIN" install) >>"$LOG_FILE" 2>&1
  fi
  if frontend_needs_build "$frontend"; then
    notify "Building UI"
    log "Running npm run build..."
    (cd "$frontend" && "$NPM_BIN" run build) >>"$LOG_FILE" 2>&1
  else
    log "UI build is up to date."
  fi
}

start_services() {
  local frontend="$ROOT/proof_of_concept_ui/frontend"
  export PLATSWAP_ROOT="$ROOT"
  export PLUGGY_API_BASE_URL="http://127.0.0.1:8787"

  if ! port_in_use 8787; then
    log "Starting backend..."
    (
      cd "$ROOT"
      nohup "$ROOT/.venv/bin/python" "$ROOT/run_web.py" >>"$LOG_FILE" 2>&1 < /dev/null &
      backend_pid="$!"
      echo "$backend_pid" >"$BACKEND_PID_FILE"
      disown "$backend_pid" >/dev/null 2>&1 || true
    )
  else
    log "Backend already running on 8787."
  fi

  if ! port_in_use 3000; then
    log "Starting frontend..."
    (
      cd "$frontend"
      nohup "$NPM_BIN" run start -- -p 3000 >>"$LOG_FILE" 2>&1 < /dev/null &
      frontend_pid="$!"
      echo "$frontend_pid" >"$FRONTEND_PID_FILE"
      disown "$frontend_pid" >/dev/null 2>&1 || true
    )
  else
    log "Frontend already running on 3000."
  fi
}

write_splash_page() {
  SPLASH_FILE="$LOG_DIR/launch-splash.html"
  cat >"$SPLASH_FILE" <<'HTML'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Pluggy Launching</title>
  <style>
    :root { color-scheme: dark; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
      display: grid;
      place-items: center;
      background: radial-gradient(circle at 20% 20%, #2a354a 0%, #10141e 55%, #090c13 100%);
      color: #eef2ff;
    }
    .card {
      width: min(540px, 92vw);
      border-radius: 16px;
      border: 1px solid rgba(255,255,255,0.16);
      background: rgba(16, 20, 30, 0.7);
      backdrop-filter: blur(10px);
      padding: 28px 24px;
      box-shadow: 0 28px 90px rgba(4, 8, 20, 0.45);
    }
    .title {
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin: 0;
    }
    .subtitle {
      margin: 8px 0 18px;
      color: rgba(232, 238, 255, 0.84);
      font-size: 14px;
    }
    .progress-wrap {
      height: 12px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.2);
      overflow: hidden;
      background: rgba(0, 0, 0, 0.25);
    }
    .progress {
      height: 100%;
      width: 10%;
      border-radius: 999px;
      background: linear-gradient(90deg, #53e2ff 0%, #6df3c8 50%, #ffe083 100%);
      transition: width .28s ease;
    }
    .status {
      margin-top: 12px;
      font-size: 13px;
      color: rgba(232, 238, 255, 0.9);
    }
    .hint {
      margin-top: 10px;
      font-size: 12px;
      color: rgba(210, 220, 245, 0.7);
    }
    .timer {
      margin-top: 6px;
      font-size: 12px;
      color: rgba(210, 220, 245, 0.75);
    }
  </style>
</head>
<body>
  <section class="card">
    <h1 class="title">Pluggy</h1>
    <p class="subtitle">Starting services and preparing your workspace...</p>
    <div class="progress-wrap"><div class="progress" id="bar"></div></div>
    <p class="status" id="status">Starting backend...</p>
    <p class="timer" id="timer">0s elapsed</p>
    <p class="hint">This screen will close automatically when Pluggy is ready.</p>
  </section>
  <script>
    const bar = document.getElementById("bar");
    const status = document.getElementById("status");
    const timerText = document.getElementById("timer");
    const targetUrl = "http://localhost:3000";
    const startedAt = Date.now();
    const minDisplayMs = 9000;
    let networkHits = 0;
    let progress = 12;
    const phases = [
      { at: 18, text: "Starting backend..." },
      { at: 42, text: "Starting frontend..." },
      { at: 68, text: "Warming providers..." },
      { at: 91, text: "Preparing home rails..." },
      { at: 96, text: "Opening Pluggy..." }
    ];
    function paint() {
      bar.style.width = `${Math.min(progress, 100)}%`;
      for (const phase of phases) {
        if (progress >= phase.at) status.textContent = phase.text;
      }
      if (timerText) {
        timerText.textContent = `${Math.floor((Date.now() - startedAt) / 1000)}s elapsed`;
      }
    }
    async function probe() {
      const timedOut = Date.now() - startedAt > 55000;
      try {
        // Use no-cors from file:// splash to avoid browser CORS blocks.
        await fetch(targetUrl, { mode: "no-cors", cache: "no-store" });
        networkHits += 1;
        const ready = networkHits >= 2 && (Date.now() - startedAt) >= minDisplayMs;
        if (!ready && !timedOut) {
          return false;
        }
        progress = 100;
        paint();
        status.textContent = "Ready. Opening Pluggy...";
        const wait = Math.max(250, minDisplayMs - (Date.now() - startedAt));
        setTimeout(() => { window.location.replace(targetUrl); }, wait);
        return true;
      } catch {
        if (timedOut) {
          progress = 100;
          paint();
          status.textContent = "Opening Pluggy...";
          const wait = Math.max(250, minDisplayMs - (Date.now() - startedAt));
          setTimeout(() => { window.location.replace(targetUrl); }, wait);
          return true;
        }
        return false;
      }
    }
    paint();
    const tick = setInterval(() => {
      progress = Math.min(progress + 1.2, 95);
      paint();
      probe().then((ready) => { if (ready) clearInterval(tick); });
    }, 450);
    setTimeout(() => {
      window.location.replace(targetUrl);
    }, 60000);
  </script>
</body>
</html>
HTML
}

ensure_venv
ensure_frontend
start_services
if [[ "${PLUGGY_WEBVIEW:-0}" == "1" ]]; then
  notify "Pluggy is starting"
  exit 0
fi
write_splash_page
/usr/bin/open "$SPLASH_FILE" >/dev/null 2>&1 || /usr/bin/open "http://localhost:3000" >/dev/null 2>&1 || true
notify "Pluggy is starting"
