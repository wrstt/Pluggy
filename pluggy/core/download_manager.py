"""
Download Manager
Manages concurrent downloads with pause/resume/cancel and event-driven updates
"""
import threading
import time
import os
from pathlib import Path
from typing import Dict, Optional
import uuid

from ..models.download_job import DownloadJob, JobStatus
from .event_bus import EventBus, Events
from .download_backends import NativeRequestsBackend, Aria2Backend
from .request_context import SessionContext, get_session, set_session


class DownloadManager:
    """Manages download queue with concurrency control"""
    
    def __init__(self, rd_client, event_bus: EventBus, max_concurrent: int = 3, settings=None):
        self.rd_client = rd_client
        self.event_bus = event_bus
        self.max_concurrent = max_concurrent
        self.settings = settings
        
        self.jobs: Dict[str, DownloadJob] = {}
        self._lock = threading.RLock()
        self._semaphore = threading.Semaphore(max_concurrent)
        self._backends = {
            "native": NativeRequestsBackend(),
            "aria2": Aria2Backend(),
        }
        self._selected_backend = self._detect_selected_backend()
    
    def queue_download(
        self,
        title: str,
        output_path: Path,
        magnet: Optional[str] = None,
        direct_url: Optional[str] = None
    ) -> DownloadJob:
        """
        Queue a new download
        
        Args:
            title: Display title
            output_path: Where to save the file
            magnet: Magnet link (will be resolved via RealDebrid)
            direct_url: Direct download URL
        
        Returns:
            DownloadJob instance
        """
        job_id = str(uuid.uuid4())
        
        job = DownloadJob(
            job_id=job_id,
            title=title,
            output_path=output_path,
            magnet=magnet,
            direct_url=direct_url
        )
        
        with self._lock:
            self.jobs[job_id] = job
        
        self.event_bus.emit(Events.DOWNLOAD_QUEUED, {"job": job})

        # Propagate request context into background download thread so per-profile
        # RealDebrid tokens and settings remain isolated.
        ctx = get_session()
        ctx_snapshot = SessionContext(
            user_id=ctx.user_id,
            username=ctx.username,
            role=ctx.role or "user",
            profile_id=ctx.profile_id,
        )

        # Start download in background thread
        threading.Thread(
            target=self._process_job,
            args=(job, ctx_snapshot),
            daemon=True
        ).start()
	        
        return job
	    
    def _process_job(self, job: DownloadJob, ctx_snapshot: Optional[SessionContext] = None):
        """Process a download job with semaphore control"""
        if ctx_snapshot is not None:
            set_session(ctx_snapshot)
        with self._semaphore:
            try:
                def _status_update(message: str):
                    job.status_detail = message
                    self.event_bus.emit(Events.DOWNLOAD_PROGRESS, {"job": job})

                # Resolve magnet if needed
                if job.magnet:
                    if not self.rd_client.is_authenticated():
                        raise Exception("RealDebrid authentication required for magnet downloads.")
                    job.status = JobStatus.RESOLVING
                    job.status_detail = "Preparing magnet..."
                    self.event_bus.emit(Events.DOWNLOAD_STARTED, {"job": job})
                    
                    urls = self.rd_client.resolve_magnet(job.magnet, status_callback=_status_update)
                    if not urls:
                        raise Exception("Failed to resolve magnet link")
                    
                    # Use first URL for now
                    direct_url = urls[0] if isinstance(urls, list) else urls
                else:
                    direct_url = job.direct_url

                # Handle direct .torrent links through RealDebrid if possible.
                if direct_url and self._is_torrent_reference(direct_url):
                    if not self.rd_client.is_authenticated():
                        raise Exception("RealDebrid authentication required for torrent-link downloads.")
                    job.status = JobStatus.RESOLVING
                    job.status_detail = "Preparing torrent..."
                    self.event_bus.emit(Events.DOWNLOAD_STARTED, {"job": job})
                    urls = self.rd_client.resolve_torrent_url(direct_url, status_callback=_status_update)
                    if not urls:
                        raise Exception("Failed to resolve torrent link")
                    direct_url = urls[0] if isinstance(urls, list) else urls
                
                if not direct_url:
                    raise Exception("No download URL available")
                
                # Download file
                job.status_detail = ""
                self._download_file(job, direct_url)
                
                # Mark complete if not cancelled
                if not job.is_cancelled:
                    job.status = JobStatus.COMPLETED
                    job.status_detail = ""
                    job.end_time = time.time()
                    self.event_bus.emit(Events.DOWNLOAD_COMPLETED, {"job": job})
            
            except Exception as e:
                job.status = JobStatus.ERROR
                job.error = str(e)
                job.status_detail = ""
                job.end_time = time.time()
                self.event_bus.emit(Events.DOWNLOAD_ERROR, {
                    "job": job,
                    "error": str(e)
                })

    def _is_torrent_reference(self, url: str) -> bool:
        low = (url or "").lower()
        return (
            low.endswith(".torrent")
            or "/dl.php?t=" in low
            or "download.php?id=" in low
            or "viewtopic.php?t=" in low
        )
    
    def _detect_selected_backend(self) -> str:
        selected = "native"
        if self.settings is not None:
            selected = str(self.settings.get("download_backend", "native") or "native").strip().lower()
        if selected not in self._backends:
            selected = "native"
        return selected

    def set_download_backend(self, name: str):
        name = (name or "native").strip().lower()
        if name not in self._backends:
            name = "native"
        self._selected_backend = name
        if self.settings is not None:
            self.settings.set("download_backend", name)

    def get_download_backend(self) -> str:
        return self._selected_backend

    def _download_file(self, job: DownloadJob, url: str):
        """
        Download file via configured backend.
        """
        job.status = JobStatus.DOWNLOADING
        job.status_detail = ""
        backend = self._backends.get(self._selected_backend, self._backends["native"])
        if not backend.is_available():
            fallback = self._backends["native"]
            job.status_detail = f"{self._selected_backend} unavailable, using native backend."
            self.event_bus.emit(Events.DOWNLOAD_PROGRESS, {"job": job})
            backend = fallback

        result = backend.download(
            job=job,
            url=url,
            emit_progress=lambda j: self.event_bus.emit(Events.DOWNLOAD_PROGRESS, {"job": j}),
            is_cancelled=lambda: job.is_cancelled,
            is_paused=lambda: job.is_paused,
        )
        if not result.completed and result.error:
            raise Exception(result.error)
    
    def pause_download(self, job_id: str):
        """Pause a download"""
        with self._lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.pause()
                job.status_detail = ""
                self.event_bus.emit(Events.DOWNLOAD_PAUSED, {"job": job})
    
    def resume_download(self, job_id: str):
        """Resume a paused download"""
        with self._lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.resume()
                job.status_detail = ""
                self.event_bus.emit(Events.DOWNLOAD_RESUMED, {"job": job})
    
    def cancel_download(self, job_id: str):
        """Cancel a download"""
        with self._lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.cancel()
                job.status_detail = ""
                self.event_bus.emit(Events.DOWNLOAD_CANCELLED, {"job": job})

    def delete_download(self, job_id: str, delete_file: bool = False):
        """Delete a job from the manager, optionally deleting its file."""
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            if delete_file:
                try:
                    path = Path(job.output_path)
                    if path.exists() and path.is_file():
                        os.remove(path)
                except Exception:
                    pass
            del self.jobs[job_id]
            self.event_bus.emit(Events.DOWNLOAD_DELETED, {"job_id": job_id, "job": job})

    def retry_download(self, job_id: str) -> Optional[DownloadJob]:
        """Retry a failed/cancelled job by queueing a new one with same payload."""
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return None
            if job.status not in {JobStatus.ERROR, JobStatus.CANCELLED}:
                return None
            return self.queue_download(
                title=f"{job.title} (retry)",
                output_path=Path(job.output_path),
                magnet=job.magnet,
                direct_url=job.direct_url,
            )
    
    def get_job(self, job_id: str) -> Optional[DownloadJob]:
        """Get a job by ID"""
        with self._lock:
            return self.jobs.get(job_id)
    
    def get_all_jobs(self) -> Dict[str, DownloadJob]:
        """Get all jobs"""
        with self._lock:
            return self.jobs.copy()
    
    def set_max_concurrent(self, max_concurrent: int):
        """Update max concurrent downloads"""
        self.max_concurrent = max_concurrent
        # Note: Changing semaphore value at runtime is complex,
        # this will take effect for new downloads
        self._semaphore = threading.Semaphore(max_concurrent)
