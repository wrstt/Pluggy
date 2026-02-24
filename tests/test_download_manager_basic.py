import http.server
import socketserver
import tempfile
import threading
import time
import unittest
from pathlib import Path

from pluggy.core.download_manager import DownloadManager
from pluggy.core.event_bus import EventBus, Events
from pluggy.core.settings_manager import SettingsManager
from pluggy.services.realdebrid_client import RealDebridClient


class BytesHandler(http.server.BaseHTTPRequestHandler):
    payload = b"x" * 4096

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, format, *args):
        return


class TestDownloadManagerBasic(unittest.TestCase):
    def test_direct_download_and_delete(self):
        with socketserver.TCPServer(("127.0.0.1", 0), BytesHandler) as httpd:
            port = httpd.server_address[1]
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()

            bus = EventBus()
            dm = DownloadManager(RealDebridClient(SettingsManager(), bus), bus, max_concurrent=1)

            events = []
            for ev in [Events.DOWNLOAD_QUEUED, Events.DOWNLOAD_COMPLETED, Events.DOWNLOAD_DELETED]:
                bus.subscribe(ev, lambda d, ev=ev: events.append(ev))

            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "payload.bin"
                job = dm.queue_download(
                    title="local-http",
                    output_path=out,
                    direct_url=f"http://127.0.0.1:{port}/payload.bin",
                )

                for _ in range(50):
                    time.sleep(0.1)
                    if job.status.value in {"completed", "error", "cancelled"}:
                        break

                self.assertEqual(job.status.value, "completed")
                self.assertTrue(out.exists())
                self.assertEqual(out.stat().st_size, 4096)

                dm.delete_download(job.job_id, delete_file=True)
                self.assertFalse(out.exists())

            httpd.shutdown()
            self.assertIn(Events.DOWNLOAD_QUEUED, events)
            self.assertIn(Events.DOWNLOAD_COMPLETED, events)
            self.assertIn(Events.DOWNLOAD_DELETED, events)


if __name__ == "__main__":
    unittest.main()
