"""
Download Job Model
Tracks download state with pause/resume/cancel capabilities
"""
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import threading
import time
from enum import Enum


class JobStatus(Enum):
    """Download job status"""
    QUEUED = "queued"
    RESOLVING = "resolving"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class DownloadJob:
    """Represents a download job with progress tracking"""
    job_id: str
    title: str
    output_path: Path
    magnet: Optional[str] = None
    direct_url: Optional[str] = None
    
    # State
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0  # 0-100
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed_kbps: float = 0.0
    error: Optional[str] = None
    status_detail: str = ""
    
    # Control events
    _pause_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    
    # Timing
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    
    def pause(self):
        """Pause the download"""
        if self.status == JobStatus.DOWNLOADING:
            self._pause_event.set()
            self.status = JobStatus.PAUSED
    
    def resume(self):
        """Resume the download"""
        if self.status == JobStatus.PAUSED:
            self._pause_event.clear()
            self.status = JobStatus.DOWNLOADING
    
    def cancel(self):
        """Cancel the download"""
        self._cancel_event.set()
        self.status = JobStatus.CANCELLED
    
    @property
    def is_paused(self) -> bool:
        """Check if paused"""
        return self._pause_event.is_set()
    
    @property
    def is_cancelled(self) -> bool:
        """Check if cancelled"""
        return self._cancel_event.is_set()
    
    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds"""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time
    
    @property
    def eta_seconds(self) -> Optional[float]:
        """Estimate time remaining in seconds"""
        if self.speed_kbps > 0 and self.total_bytes > 0:
            remaining_bytes = self.total_bytes - self.downloaded_bytes
            remaining_kb = remaining_bytes / 1024
            return remaining_kb / self.speed_kbps
        return None
    
    @property
    def speed_formatted(self) -> str:
        """Get formatted speed string"""
        if self.speed_kbps < 1024:
            return f"{self.speed_kbps:.1f} KB/s"
        else:
            return f"{self.speed_kbps / 1024:.1f} MB/s"

    @property
    def status_display(self) -> str:
        """Status with optional detail text."""
        if self.status_detail:
            return f"{self.status.value}: {self.status_detail}"
        return self.status.value
