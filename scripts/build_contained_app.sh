#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="$ROOT/proof_of_concept_ui/frontend"
APP="$ROOT/Pluggy_Contained.app"
APP_VERSION="1.0"
MACOS_MIN_VERSION="${PLUGGY_MACOS_MIN_VERSION:-11.0}"
STAGE="$ROOT/.build-contained"
RUNTIME_STAGE="$STAGE/runtime_template"
ICONSET_SOURCE="$ROOT/branding/tahoe_icon_pack/Pluggy_Tahoe_Glass_Icons/PluggyLight.appiconset"
ICON_SOURCE="$ROOT/logo.png"
if [[ -f "$ROOT/branding/tahoe_icon_pack/Pluggy_Tahoe_Glass_Icons/pluggy_tahoe_glass_light_1024.png" ]]; then
  ICON_SOURCE="$ROOT/branding/tahoe_icon_pack/Pluggy_Tahoe_Glass_Icons/pluggy_tahoe_glass_light_1024.png"
fi

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1"
}

swift_macos_target() {
  local arch
  arch="$(uname -m)"
  case "$arch" in
    arm64|x86_64)
      printf '%s-apple-macos%s' "$arch" "$MACOS_MIN_VERSION"
      ;;
    *)
      echo "Unsupported architecture for Swift app launcher: $arch" >&2
      exit 1
      ;;
  esac
}

need_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

need_cmd /usr/bin/python3
need_cmd /usr/bin/swiftc
need_cmd /usr/bin/rsync
need_cmd /usr/bin/ditto
need_cmd /usr/bin/sips
need_cmd /usr/bin/iconutil

build_icns() {
  local source_png="$1"
  local output_icns="$2"
  local iconset_dir="$STAGE/AppIcon.iconset"
  rm -rf "$iconset_dir"
  mkdir -p "$iconset_dir"
  /usr/bin/sips -z 16 16 "$source_png" --out "$iconset_dir/icon_16x16.png" >/dev/null
  /usr/bin/sips -z 32 32 "$source_png" --out "$iconset_dir/icon_16x16@2x.png" >/dev/null
  /usr/bin/sips -z 32 32 "$source_png" --out "$iconset_dir/icon_32x32.png" >/dev/null
  /usr/bin/sips -z 64 64 "$source_png" --out "$iconset_dir/icon_32x32@2x.png" >/dev/null
  /usr/bin/sips -z 128 128 "$source_png" --out "$iconset_dir/icon_128x128.png" >/dev/null
  /usr/bin/sips -z 256 256 "$source_png" --out "$iconset_dir/icon_128x128@2x.png" >/dev/null
  /usr/bin/sips -z 256 256 "$source_png" --out "$iconset_dir/icon_256x256.png" >/dev/null
  /usr/bin/sips -z 512 512 "$source_png" --out "$iconset_dir/icon_256x256@2x.png" >/dev/null
  /usr/bin/sips -z 512 512 "$source_png" --out "$iconset_dir/icon_512x512.png" >/dev/null
  /usr/bin/sips -z 1024 1024 "$source_png" --out "$iconset_dir/icon_512x512@2x.png" >/dev/null
  /usr/bin/iconutil -c icns "$iconset_dir" -o "$output_icns"
}

build_icns_from_iconset() {
  local source_iconset="$1"
  local output_icns="$2"
  local iconset_dir="$STAGE/AppIcon.iconset"
  rm -rf "$iconset_dir"
  mkdir -p "$iconset_dir"
  /usr/bin/rsync -a "$source_iconset/" "$iconset_dir/"
  /usr/bin/iconutil -c icns "$iconset_dir" -o "$output_icns"
}

if command -v npm >/dev/null 2>&1; then
  NPM_BIN="$(command -v npm)"
elif [[ -x /opt/homebrew/bin/npm ]]; then
  NPM_BIN="/opt/homebrew/bin/npm"
elif [[ -x /usr/local/bin/npm ]]; then
  NPM_BIN="/usr/local/bin/npm"
else
  echo "npm is required to build the contained app." >&2
  exit 1
fi

NODE_RUNTIME_STAGE="$STAGE/node-runtime"
NODE_VERSION="22.14.0"
ARCH="$(uname -m)"
if [[ "$ARCH" == "arm64" ]]; then
  NODE_ARCH="arm64"
elif [[ "$ARCH" == "x86_64" ]]; then
  NODE_ARCH="x64"
else
  echo "Unsupported architecture for bundled Node: $ARCH" >&2
  exit 1
fi
NODE_TARBALL="node-v${NODE_VERSION}-darwin-${NODE_ARCH}.tar.gz"
NODE_DIRNAME="node-v${NODE_VERSION}-darwin-${NODE_ARCH}"
NODE_URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_TARBALL}"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  log "Creating .venv..."
  /usr/bin/python3 -m venv "$ROOT/.venv"
fi

log "Installing backend dependencies..."
"$ROOT/.venv/bin/python" -m pip install -U pip >/dev/null
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements-web.txt" >/dev/null
"$ROOT/.venv/bin/python" -m pip install pyinstaller >/dev/null

log "Installing frontend dependencies..."
(cd "$FRONTEND" && "$NPM_BIN" install)

log "Building frontend standalone..."
(cd "$FRONTEND" && "$NPM_BIN" run build)

if [[ ! -f "$FRONTEND/.next/standalone/server.js" ]]; then
  echo "Next standalone output missing (.next/standalone/server.js)." >&2
  exit 1
fi

rm -rf "$STAGE"
mkdir -p "$RUNTIME_STAGE/frontend" "$RUNTIME_STAGE/backend" "$RUNTIME_STAGE/bin"

log "Bundling frontend runtime..."
/usr/bin/rsync -a "$FRONTEND/.next/standalone/" "$RUNTIME_STAGE/frontend/"
mkdir -p "$RUNTIME_STAGE/frontend/.next/static"
/usr/bin/rsync -a "$FRONTEND/.next/static/" "$RUNTIME_STAGE/frontend/.next/static/"
if [[ -d "$FRONTEND/public" ]]; then
  /usr/bin/rsync -a "$FRONTEND/public/" "$RUNTIME_STAGE/frontend/public/"
fi
mkdir -p "$RUNTIME_STAGE/frontend/data"
# Always ship an empty auth seed file in the contained app runtime template.
# This prevents accidentally packaging local test users from a modified repo file.
cat > "$RUNTIME_STAGE/frontend/data/auth-users.json" <<'EOF'
{
  "users": []
}
EOF

log "Building bundled backend binary..."
"$ROOT/.venv/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --onefile \
  --name PluggyBackend \
  --distpath "$STAGE/dist" \
  --workpath "$STAGE/build" \
  --specpath "$STAGE/spec" \
  "$ROOT/run_web.py" >/dev/null
cp "$STAGE/dist/PluggyBackend" "$RUNTIME_STAGE/backend/PluggyBackend"
chmod +x "$RUNTIME_STAGE/backend/PluggyBackend"

log "Fetching portable Node runtime..."
mkdir -p "$NODE_RUNTIME_STAGE"
if [[ ! -x "$NODE_RUNTIME_STAGE/$NODE_DIRNAME/bin/node" ]]; then
  rm -rf "$NODE_RUNTIME_STAGE/$NODE_DIRNAME"
  curl -L -o "$NODE_RUNTIME_STAGE/$NODE_TARBALL" "$NODE_URL"
  tar -xzf "$NODE_RUNTIME_STAGE/$NODE_TARBALL" -C "$NODE_RUNTIME_STAGE"
fi
log "Copying Node runtime..."
cp "$NODE_RUNTIME_STAGE/$NODE_DIRNAME/bin/node" "$RUNTIME_STAGE/bin/node"
chmod +x "$RUNTIME_STAGE/bin/node"

cat > "$RUNTIME_STAGE/VERSION" <<EOF
runtime_version=3
built_at_utc=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF

LAUNCHER="$STAGE/launch_platswap.sh"
cat > "$LAUNCHER" <<'LAUNCH'
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUNDLED_TEMPLATE="$SCRIPT_DIR/runtime_template"
APP_SUPPORT="$HOME/Library/Application Support/Pluggy Official"
CONTAINED_RUNTIME="$APP_SUPPORT/runtime"
LOG_DIR="$APP_SUPPORT/logs"
LOG_FILE="$LOG_DIR/launch.log"
LOCK_DIR="/tmp/pluggy-contained-launch.lock"
THROTTLE_FILE="/tmp/pluggy-contained-launch.last"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"
MODE="contained"
ROOT=""
SPLASH_FILE=""

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

mkdir -p "$LOG_DIR"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >>"$LOG_FILE"
}

notify() {
  local msg="$1"
  /usr/bin/osascript -e "display notification \"$msg\" with title \"Pluggy\"" >/dev/null 2>&1 || true
}

alert() {
  local msg="$1"
  /usr/bin/osascript -e "display alert \"Pluggy\" message \"$msg\"" >/dev/null 2>&1 || true
}

has_dev_root() {
  local candidate="$1"
  [[ -n "$candidate" && -f "$candidate/run_web.py" && -d "$candidate/proof_of_concept_ui/frontend" ]]
}

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  exit 0
fi
cleanup_lock() { rmdir "$LOCK_DIR" >/dev/null 2>&1 || true; }
trap cleanup_lock EXIT

now_epoch="$(date +%s)"
last_epoch="0"
if [[ -f "$THROTTLE_FILE" ]]; then
  last_epoch="$(cat "$THROTTLE_FILE" 2>/dev/null || echo 0)"
fi
if [[ "$last_epoch" =~ ^[0-9]+$ ]] && (( now_epoch - last_epoch < 8 )); then
  exit 0
fi
printf '%s\n' "$now_epoch" >"$THROTTLE_FILE"

DEV_ROOT="${PLUGGY_DEV_ROOT:-}"
if [[ -z "$DEV_ROOT" && -f "$APP_SUPPORT/dev-root.txt" ]]; then
  DEV_ROOT="$(cat "$APP_SUPPORT/dev-root.txt" 2>/dev/null || true)"
fi

if has_dev_root "$DEV_ROOT"; then
  MODE="dev"
  ROOT="$DEV_ROOT"
  log "Mode: dev (PLUGGY_DEV_ROOT=$ROOT)"
else
  MODE="contained"
  ROOT="$CONTAINED_RUNTIME"
  log "Mode: contained"
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

spawn_detached() {
  local cwd="$1"
  shift
  /usr/bin/python3 - "$cwd" "$LOG_FILE" "$@" <<'PY'
import os
import subprocess
import sys

cwd = sys.argv[1]
log_file = sys.argv[2]
cmd = sys.argv[3:]

with open(log_file, "ab", buffering=0) as handle:
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=handle,
        start_new_session=True,
        env=os.environ.copy(),
    )
print(proc.pid)
PY
}

stop_existing_services() {
  for pid_file in "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"; do
    if [[ -f "$pid_file" ]]; then
      pid="$(cat "$pid_file" 2>/dev/null || true)"
      if [[ "$pid" =~ ^[0-9]+$ ]]; then
        kill "$pid" >/dev/null 2>&1 || true
      fi
      rm -f "$pid_file"
    fi
  done
}

prepare_contained_runtime() {
  if [[ ! -d "$BUNDLED_TEMPLATE" ]]; then
    log "Missing bundled runtime template: $BUNDLED_TEMPLATE"
    alert "Launch failed: bundled runtime missing."
    exit 1
  fi

  if [[ "${PLUGGY_RESET_RUNTIME:-0}" == "1" ]]; then
    log "Resetting contained runtime by request."
    rm -rf "$CONTAINED_RUNTIME"
  fi

  local bundled_version="$BUNDLED_TEMPLATE/VERSION"
  local runtime_version="$CONTAINED_RUNTIME/VERSION"
  local needs_refresh="0"

  if [[ ! -f "$CONTAINED_RUNTIME/.initialized" ]]; then
    needs_refresh="1"
  elif [[ -f "$bundled_version" ]]; then
    if [[ ! -f "$runtime_version" ]]; then
      needs_refresh="1"
    elif ! cmp -s "$bundled_version" "$runtime_version"; then
      needs_refresh="1"
    fi
  fi

  if [[ "$needs_refresh" == "1" ]]; then
    log "Initializing contained runtime in $CONTAINED_RUNTIME"
    # Ensure stale processes do not keep serving an old runtime after refresh.
    stop_existing_services
    rm -rf "$CONTAINED_RUNTIME"
    mkdir -p "$CONTAINED_RUNTIME"
    /usr/bin/rsync -a "$BUNDLED_TEMPLATE/" "$CONTAINED_RUNTIME/"
    touch "$CONTAINED_RUNTIME/.initialized"
  fi
}

prepare_dev_runtime() {
  if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
    log "Missing dev virtualenv at $ROOT/.venv/bin/python"
    alert "Dev mode failed: missing .venv in PLUGGY_DEV_ROOT."
    exit 1
  fi
  local frontend="$ROOT/proof_of_concept_ui/frontend"
  if [[ ! -d "$frontend/.next" ]]; then
    local npm_bin=""
    if command -v npm >/dev/null 2>&1; then
      npm_bin="$(command -v npm)"
    elif [[ -x /opt/homebrew/bin/npm ]]; then
      npm_bin="/opt/homebrew/bin/npm"
    elif [[ -x /usr/local/bin/npm ]]; then
      npm_bin="/usr/local/bin/npm"
    fi
    if [[ -z "$npm_bin" ]]; then
      log "npm not found for dev mode build."
      alert "Dev mode failed: npm not found."
      exit 1
    fi
    log "Dev mode: building frontend."
    (cd "$frontend" && "$npm_bin" install && "$npm_bin" run build) >>"$LOG_FILE" 2>&1
  fi
}

start_services_contained() {
  local node_bin="$ROOT/bin/node"
  local backend_bin="$ROOT/backend/PluggyBackend"
  local frontend_dir="$ROOT/frontend"
  local data_dir="$APP_SUPPORT/data"

  if [[ ! -x "$node_bin" || ! -x "$backend_bin" || ! -f "$frontend_dir/server.js" ]]; then
    log "Contained runtime incomplete."
    alert "Launch failed: contained runtime incomplete."
    exit 1
  fi

  export PLUGGY_API_BASE_URL="http://127.0.0.1:8787"
  export PLATSWAP_AUTH_SECRET="${PLATSWAP_AUTH_SECRET:-pluggy-contained-local-secret}"
  export PLUGGY_DATA_DIR="$data_dir"
  mkdir -p "$PLUGGY_DATA_DIR"

  if ! port_in_use 8787; then
    log "Starting contained backend..."
    backend_pid="$(spawn_detached "$ROOT" "$backend_bin")"
    echo "$backend_pid" >"$BACKEND_PID_FILE"
  else
    log "Backend already running on 8787."
  fi

  # Ensure the backend is actually responsive before starting the frontend.
  # Next standalone will eagerly hit /api/auth/status during initial page loads.
  local ready="0"
  for i in {1..80}; do
    if curl -fsS "http://127.0.0.1:8787/health" >/dev/null 2>&1; then
      ready="1"
      break
    fi
    sleep 0.15
  done
  if [[ "$ready" != "1" ]]; then
    log "Backend did not become ready in time; continuing anyway."
  fi

  if ! port_in_use 3000; then
    log "Starting contained frontend..."
    frontend_pid="$(spawn_detached "$frontend_dir" env PORT=3000 HOSTNAME=127.0.0.1 PLUGGY_API_BASE_URL=http://127.0.0.1:8787 "$node_bin" server.js)"
    echo "$frontend_pid" >"$FRONTEND_PID_FILE"
  else
    log "Frontend already running on 3000."
  fi
}

start_services_dev() {
  local frontend="$ROOT/proof_of_concept_ui/frontend"
  local npm_bin=""
  if command -v npm >/dev/null 2>&1; then
    npm_bin="$(command -v npm)"
  elif [[ -x /opt/homebrew/bin/npm ]]; then
    npm_bin="/opt/homebrew/bin/npm"
  elif [[ -x /usr/local/bin/npm ]]; then
    npm_bin="/usr/local/bin/npm"
  fi

  if [[ -z "$npm_bin" ]]; then
    log "Dev mode: npm not found."
    alert "Dev mode failed: npm not found."
    exit 1
  fi

  export PLATSWAP_ROOT="$ROOT"
  export PLUGGY_API_BASE_URL="http://127.0.0.1:8787"

  if ! port_in_use 8787; then
    log "Starting dev backend..."
    backend_pid="$(spawn_detached "$ROOT" "$ROOT/.venv/bin/python" "$ROOT/run_web.py")"
    echo "$backend_pid" >"$BACKEND_PID_FILE"
  else
    log "Backend already running on 8787."
  fi

  if ! port_in_use 3000; then
    log "Starting dev frontend..."
    frontend_pid="$(spawn_detached "$frontend" "$npm_bin" run start -- -p 3000)"
    echo "$frontend_pid" >"$FRONTEND_PID_FILE"
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
    .subtitle { margin: 8px 0 18px; color: rgba(232, 238, 255, 0.84); font-size: 14px; }
    .progress-wrap { height: 12px; border-radius: 999px; border: 1px solid rgba(255,255,255,0.2); overflow: hidden; background: rgba(0,0,0,0.25); }
    .progress { height: 100%; width: 12%; border-radius: 999px; background: linear-gradient(90deg, #53e2ff 0%, #6df3c8 50%, #ffe083 100%); transition: width .24s ease; }
    .status { margin-top: 12px; font-size: 13px; color: rgba(232, 238, 255, 0.9); }
    .timer { margin-top: 8px; font-size: 12px; color: rgba(210, 220, 245, 0.75); }
  </style>
</head>
<body>
  <section class="card">
    <h1 class="title">Pluggy</h1>
    <p class="subtitle">Launching services...</p>
    <div class="progress-wrap"><div class="progress" id="bar"></div></div>
    <p class="status" id="status">Booting runtime...</p>
    <p class="timer" id="timer">0s elapsed</p>
  </section>
  <script>
    const targetUrl = "http://127.0.0.1:3000";
    const startedAt = Date.now();
    const minDisplayMs = 9000;
    let networkHits = 0;
    const milestones = [
      { at: 10, text: "Booting runtime..." },
      { at: 35, text: "Starting backend..." },
      { at: 58, text: "Starting frontend..." },
      { at: 80, text: "Warming providers..." },
      { at: 91, text: "Preparing home rails..." },
      { at: 96, text: "Opening Pluggy..." }
    ];

    function setUI(progress) {
      const bar = document.getElementById("bar");
      const status = document.getElementById("status");
      const timer = document.getElementById("timer");
      if (bar) bar.style.width = progress + "%";
      if (status) {
        let text = "Launching...";
        for (const milestone of milestones) {
          if (progress >= milestone.at) text = milestone.text;
        }
        status.textContent = text;
      }
      if (timer) {
        timer.textContent = `${Math.floor((Date.now() - startedAt) / 1000)}s elapsed`;
      }
    }

    let progress = 8;
    setUI(progress);
    const ticker = setInterval(() => {
      progress = Math.min(96, progress + 1.8);
      setUI(progress);
    }, 260);

    async function ready() {
      const elapsed = Date.now() - startedAt;
      try {
        await fetch(targetUrl, { mode: "no-cors", cache: "no-store" });
        networkHits += 1;
        return networkHits >= 2 && elapsed >= minDisplayMs;
      } catch {
        return false;
      }
    }

    async function loop() {
      const ok = await ready();
      const timedOut = Date.now() - startedAt > 55000;
      if (ok || timedOut) {
        clearInterval(ticker);
        setUI(100);
        const wait = Math.max(250, minDisplayMs - (Date.now() - startedAt));
        setTimeout(() => window.location.replace(targetUrl), wait);
        return;
      }
      setTimeout(loop, 450);
    }
    loop();
    setTimeout(() => window.location.replace(targetUrl), 60000);
  </script>
</body>
</html>
HTML
}

if [[ "$MODE" == "contained" ]]; then
  prepare_contained_runtime
  start_services_contained
else
  prepare_dev_runtime
  start_services_dev
fi

if [[ "${PLUGGY_WEBVIEW:-0}" == "1" ]]; then
  notify "Pluggy is starting"
  exit 0
fi

write_splash_page
/usr/bin/open "$SPLASH_FILE" >/dev/null 2>&1 || /usr/bin/open "http://127.0.0.1:3000" >/dev/null 2>&1 || true
notify "Pluggy is starting"
LAUNCH
chmod +x "$LAUNCHER"

log "Building macOS app bundle..."
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$LAUNCHER" "$APP/Contents/Resources/launch_platswap.sh"
chmod +x "$APP/Contents/Resources/launch_platswap.sh"
/usr/bin/rsync -a "$RUNTIME_STAGE/" "$APP/Contents/Resources/runtime_template/"
if [[ -d "$ICONSET_SOURCE" ]]; then
  build_icns_from_iconset "$ICONSET_SOURCE" "$APP/Contents/Resources/AppIcon.icns"
  cp "$ICON_SOURCE" "$APP/Contents/Resources/AppTitleIcon.png"
elif [[ -f "$ICON_SOURCE" ]]; then
  build_icns "$ICON_SOURCE" "$APP/Contents/Resources/AppIcon.icns"
  cp "$ICON_SOURCE" "$APP/Contents/Resources/AppTitleIcon.png"
fi

SWIFT_TARGET="$(swift_macos_target)"
log "Building WebView launcher for target $SWIFT_TARGET"
/usr/bin/swiftc \
  -target "$SWIFT_TARGET" \
  -framework AppKit \
  -framework WebKit \
  "$ROOT/scripts/PluggyWebView.swift" \
  -o "$APP/Contents/MacOS/Pluggy"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>Pluggy</string>
  <key>CFBundleDisplayName</key>
  <string>Pluggy</string>
  <key>CFBundleIdentifier</key>
  <string>com.pluggy.contained</string>
  <key>CFBundleVersion</key>
  <string>${APP_VERSION}</string>
  <key>CFBundleShortVersionString</key>
  <string>${APP_VERSION}</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleExecutable</key>
  <string>Pluggy</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundleIconName</key>
  <string>AppIcon</string>
  <key>LSMinimumSystemVersion</key>
  <string>${MACOS_MIN_VERSION}</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

/usr/bin/codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
/usr/bin/xattr -dr com.apple.quarantine "$APP" >/dev/null 2>&1 || true

echo "Built contained app: $APP"
echo "Runtime copy target on first launch: ~/Library/Application Support/Pluggy Official/runtime"
echo "Dev override: set PLUGGY_DEV_ROOT=/path/to/1.0 before launching"
