import http.server
import socketserver
import tempfile
import threading
import time
import unittest
from pathlib import Path

from pluggy.core.download_manager import DownloadManager
from pluggy.core.event_bus import EventBus
from pluggy.core.settings_manager import SettingsManager
from pluggy.models.download_job import JobStatus
from pluggy.services.realdebrid_client import RealDebridClient


class BytesHandler(http.server.BaseHTTPRequestHandler):
    payload = b"y" * 2048

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, format, *args):
        return


class FakeUnavailableBackend:
    name = "aria2"
    def is_available(self):
        return False
    def download(self, *args, **kwargs):
        raise RuntimeError("should not be called")


class TestDownloadBackendAndRetry(unittest.TestCase):
    def test_aria2_unavailable_falls_back_to_native(self):
        with socketserver.TCPServer(("127.0.0.1", 0), BytesHandler) as httpd:
            port = httpd.server_address[1]
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()

            settings = SettingsManager()
            settings.set("download_backend", "aria2")
            bus = EventBus()
            dm = DownloadManager(RealDebridClient(settings, bus), bus, max_concurrent=1, settings=settings)
            dm._backends["aria2"] = FakeUnavailableBackend()

            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "fallback.bin"
                job = dm.queue_download(
                    title="fallback-test",
                    output_path=out,
                    direct_url=f"http://127.0.0.1:{port}/x.bin",
                )
                for _ in range(60):
                    time.sleep(0.1)
                    if job.status.value in {"completed", "error", "cancelled"}:
                        break
                self.assertEqual(job.status.value, "completed")
                self.assertTrue(out.exists())
                self.assertEqual(out.stat().st_size, 2048)

            httpd.shutdown()

    def test_retry_download_creates_new_job_from_error(self):
        settings = SettingsManager()
        bus = EventBus()
        dm = DownloadManager(RealDebridClient(settings, bus), bus, max_concurrent=1, settings=settings)

        # Use unroutable local port for quick connection error.
        job = dm.queue_download(
            title="bad-url",
            output_path=Path("/tmp/pluggy_retry_bad.bin"),
            direct_url="http://127.0.0.1:9/not_there",
        )
        for _ in range(50):
            time.sleep(0.1)
            if job.status in {JobStatus.ERROR, JobStatus.COMPLETED, JobStatus.CANCELLED}:
                break

        self.assertEqual(job.status, JobStatus.ERROR)
        new_job = dm.retry_download(job.job_id)
        self.assertIsNotNone(new_job)
        self.assertTrue(new_job.title.endswith("(retry)"))


if __name__ == "__main__":
    unittest.main()
