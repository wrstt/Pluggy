"""
Event Bus - Central event dispatching system
Provides decoupled communication between components
"""
from typing import Callable, Dict, List
import threading


class EventBus:
    """Thread-safe event bus for component communication"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.RLock()
    
    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to an event type"""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: str, callback: Callable):
        """Unsubscribe from an event type"""
        with self._lock:
            if event_type in self._subscribers:
                if callback in self._subscribers[event_type]:
                    self._subscribers[event_type].remove(callback)
    
    def emit(self, event_type: str, data=None):
        """Emit an event to all subscribers"""
        with self._lock:
            if event_type in self._subscribers:
                for callback in self._subscribers[event_type][:]:
                    try:
                        callback(data)
                    except Exception as e:
                        print(f"Error in event handler for {event_type}: {e}")
    
    def clear(self):
        """Clear all subscriptions"""
        with self._lock:
            self._subscribers.clear()


# Event types
class Events:
    # Search events
    SEARCH_STARTED = "search_started"
    SEARCH_PROGRESS = "search_progress"
    SEARCH_COMPLETED = "search_completed"
    SEARCH_ERROR = "search_error"
    
    # Download events
    DOWNLOAD_QUEUED = "download_queued"
    DOWNLOAD_STARTED = "download_started"
    DOWNLOAD_PROGRESS = "download_progress"
    DOWNLOAD_PAUSED = "download_paused"
    DOWNLOAD_RESUMED = "download_resumed"
    DOWNLOAD_COMPLETED = "download_completed"
    DOWNLOAD_CANCELLED = "download_cancelled"
    DOWNLOAD_DELETED = "download_deleted"
    DOWNLOAD_ERROR = "download_error"
    
    # RealDebrid events
    RD_AUTH_STARTED = "rd_auth_started"
    RD_AUTH_PENDING = "rd_auth_pending"
    RD_AUTH_SUCCESS = "rd_auth_success"
    RD_AUTH_FAILED = "rd_auth_failed"
    RD_TOKEN_REFRESHED = "rd_token_refreshed"
    
    # Settings events
    SETTINGS_CHANGED = "settings_changed"
    SOURCES_RELOADED = "sources_reloaded"
