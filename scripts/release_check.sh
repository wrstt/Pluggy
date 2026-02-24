#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
RUN_NETWORK="${RUN_NETWORK:-0}"

REPORT_DIR="$ROOT/.reports"
mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/release_check_$(date +%Y%m%d_%H%M%S)_$$.log"

log(){
  echo "$1" | tee -a "$REPORT_FILE"
}

log "Release Check Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "Project: $ROOT"
log "Python: $PY"

log ""
log "[1/5] Phase gate"
"$ROOT/scripts/phase_gate.sh" | tee -a "$REPORT_FILE"

log ""
log "[2/5] Settings and manager sanity"
"$PY" - <<'PY' | tee -a "$REPORT_FILE"
from pluggy.core.settings_manager import SettingsManager
from pluggy.core.download_manager import DownloadManager
from pluggy.core.event_bus import EventBus
from pluggy.services.realdebrid_client import RealDebridClient

s=SettingsManager()
assert isinstance(s.get('first_run_completed', False), bool)
assert s.get('download_backend', 'native') in {'native','aria2'}
assert isinstance(s.get('piratebay_mirror_order', []), list)
assert isinstance(s.get('x1337_mirror_order', []), list)

bus=EventBus(); rd=RealDebridClient(s,bus)
dm=DownloadManager(rd,bus,settings=s)
assert dm.get_download_backend() in {'native','aria2'}
print('settings-manager-ok')
PY

log ""
log "[3/5] Plugin loader sanity"
"$PY" - <<'PY' | tee -a "$REPORT_FILE"
from pluggy.sources.plugin_loader import SourcePluginLoader, PluginContext, default_plugin_dirs
from pluggy.core.settings_manager import SettingsManager

loader=SourcePluginLoader(default_plugin_dirs())
ctx=PluginContext(settings=SettingsManager())
_ = loader.load(ctx)
print('plugin-loader-ok', 'errors=', len(loader.last_errors))
PY

log ""
log "[4/5] Download retry/backend smoke"
"$PY" - <<'PY' | tee -a "$REPORT_FILE"
import http.server, socketserver, threading, time, tempfile
from pathlib import Path

from pluggy.core.settings_manager import SettingsManager
from pluggy.core.event_bus import EventBus
from pluggy.services.realdebrid_client import RealDebridClient
from pluggy.core.download_manager import DownloadManager
from pluggy.models.download_job import JobStatus

class H(http.server.BaseHTTPRequestHandler):
    payload=b'z'*1024
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Length', str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)
    def log_message(self, format, *args):
        return

with socketserver.TCPServer(('127.0.0.1',0), H) as httpd:
    port=httpd.server_address[1]
    t=threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    s=SettingsManager(); s.set('download_backend','native')
    bus=EventBus(); dm=DownloadManager(RealDebridClient(s,bus),bus,settings=s)

    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'x.bin'
        j=dm.queue_download('release-smoke', p, direct_url=f'http://127.0.0.1:{port}/x.bin')
        for _ in range(50):
            time.sleep(0.1)
            if j.status in {JobStatus.COMPLETED, JobStatus.ERROR, JobStatus.CANCELLED}:
                break
        assert j.status == JobStatus.COMPLETED, j.status
        assert p.exists() and p.stat().st_size == 1024

        # Retry guard: only failed/cancelled can retry
        assert dm.retry_download(j.job_id) is None

    httpd.shutdown()

print('download-smoke-ok')
PY

log ""
log "[5/5] Optional network source check (RUN_NETWORK=$RUN_NETWORK)"
if [[ "$RUN_NETWORK" == "1" ]]; then
  "$PY" - <<'PY' | tee -a "$REPORT_FILE"
from pluggy.core.settings_manager import SettingsManager
from pluggy.sources.piratebay import PirateBaySource
from pluggy.sources.x1337 import X1337Source

s=SettingsManager()
s.update({'piratebay_mirror_order':['https://tpb.party','https://thepiratebay.zone'],
          'x1337_mirror_order':['https://1337xx.to','https://1337x.to']})

pb=PirateBaySource(s); xp=X1337Source(s)
r1=pb.search('ubuntu',1); r2=xp.search('ubuntu',1)
assert len(r1)>0, 'PirateBay returned 0 results'
assert len(r2)>0, '1337x returned 0 results'
print('network-source-ok', 'pb=', len(r1), 'x1337=', len(r2), 'pb_base=', pb.base_url, 'x_base=', xp.base_url)
PY
else
  log "network-check-skipped"
fi

log ""
log "Release Check Completed: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "Report: $REPORT_FILE"

echo "$REPORT_FILE"
