"""
Download backend implementations.
Native requests backend is default; aria2 backend is optional.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import os
import shutil
import subprocess
import time
import requests

from ..models.download_job import DownloadJob


@dataclass
class DownloadBackendResult:
    completed: bool
    error: str = ""
    warning: str = ""


class DownloadBackend:
    name = "base"

    def is_available(self) -> bool:
        return True

    def download(
        self,
        job: DownloadJob,
        url: str,
        emit_progress: Callable[[DownloadJob], None],
        is_cancelled: Callable[[], bool],
        is_paused: Callable[[], bool],
    ) -> DownloadBackendResult:
        raise NotImplementedError


class NativeRequestsBackend(DownloadBackend):
    name = "native"

    def download(
        self,
        job: DownloadJob,
        url: str,
        emit_progress: Callable[[DownloadJob], None],
        is_cancelled: Callable[[], bool],
        is_paused: Callable[[], bool],
    ) -> DownloadBackendResult:
        output_path = Path(job.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        downloaded_bytes = output_path.stat().st_size if output_path.exists() else 0
        headers = {}
        if downloaded_bytes > 0:
            headers["Range"] = f"bytes={downloaded_bytes}-"

        with requests.get(url, stream=True, headers=headers, timeout=30) as response:
            response.raise_for_status()

            if "Content-Length" in response.headers:
                content_length = int(response.headers["Content-Length"])
                job.total_bytes = downloaded_bytes + content_length
            else:
                job.total_bytes = 0

            job.downloaded_bytes = downloaded_bytes
            mode = "ab" if downloaded_bytes > 0 else "wb"
            start_time = time.time()
            last_update = start_time

            with open(output_path, mode) as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if is_cancelled():
                        return DownloadBackendResult(completed=False)

                    while is_paused():
                        time.sleep(0.1)
                        if is_cancelled():
                            return DownloadBackendResult(completed=False)

                    if chunk:
                        f.write(chunk)
                        job.downloaded_bytes += len(chunk)
                        if job.total_bytes > 0:
                            job.progress = int((job.downloaded_bytes / job.total_bytes) * 100)
                        elapsed = time.time() - start_time
                        if elapsed > 0:
                            job.speed_kbps = (job.downloaded_bytes / 1024) / elapsed

                        now = time.time()
                        if now - last_update >= 0.5:
                            emit_progress(job)
                            last_update = now

        return DownloadBackendResult(completed=True)


class Aria2Backend(DownloadBackend):
    name = "aria2"

    def is_available(self) -> bool:
        return shutil.which("aria2c") is not None

    def download(
        self,
        job: DownloadJob,
        url: str,
        emit_progress: Callable[[DownloadJob], None],
        is_cancelled: Callable[[], bool],
        is_paused: Callable[[], bool],
    ) -> DownloadBackendResult:
        if not self.is_available():
            return DownloadBackendResult(completed=False, error="aria2c not found")

        output_path = Path(job.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "aria2c",
            "--allow-overwrite=true",
            "--auto-file-renaming=false",
            "--continue=true",
            "--max-connection-per-server=8",
            "--split=8",
            "--min-split-size=1M",
            "--summary-interval=0",
            "--dir", str(output_path.parent),
            "--out", output_path.name,
            url,
        ]

        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        start = time.time()
        last_size = 0
        last_tick = start
        warned_pause = False

        try:
            while proc.poll() is None:
                if is_cancelled():
                    proc.terminate()
                    return DownloadBackendResult(completed=False)

                if is_paused() and not warned_pause:
                    job.status_detail = "Pause not supported in aria2 backend."
                    emit_progress(job)
                    warned_pause = True

                if output_path.exists():
                    size = output_path.stat().st_size
                    job.downloaded_bytes = size
                    if job.total_bytes and job.total_bytes > 0:
                        job.progress = int((size / job.total_bytes) * 100)
                    now = time.time()
                    dt = max(0.001, now - last_tick)
                    delta = max(0, size - last_size)
                    job.speed_kbps = (delta / 1024) / dt
                    last_size = size
                    last_tick = now
                    emit_progress(job)
                time.sleep(0.5)

            if proc.returncode != 0:
                stderr = proc.stderr.read().decode("utf-8", errors="ignore") if proc.stderr else ""
                return DownloadBackendResult(completed=False, error=f"aria2 failed ({proc.returncode}): {stderr[:300]}")

            if output_path.exists():
                job.downloaded_bytes = output_path.stat().st_size
                job.progress = 100
            emit_progress(job)
            return DownloadBackendResult(completed=True)
        finally:
            if proc.poll() is None:
                proc.terminate()
