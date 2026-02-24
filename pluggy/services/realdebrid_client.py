"""
RealDebrid Client
Handles device OAuth flow, token management, and magnet resolution
"""
import requests
import threading
import time
from typing import Optional, Dict, List, Callable
from ..core.event_bus import EventBus, Events
from ..core.request_context import SessionContext, get_session, set_session


class RealDebridClient:
    """RealDebrid API client with OAuth support"""
    
    BASE_URL = "https://api.real-debrid.com/rest/1.0"
    OAUTH_URL = "https://api.real-debrid.com/oauth/v2"
    PUBLIC_CLIENT_ID = "X245A4XAIBGVM"
	    
    def __init__(self, settings_manager, event_bus: EventBus):
        self.settings = settings_manager
        self.event_bus = event_bus
	        
        self._polling_thread: Optional[threading.Thread] = None
        self._stop_polling = threading.Event()
        self._auth_lock = threading.RLock()

    def _timeout(self) -> float:
        try:
            return float(self.settings.get("rd_request_timeout_seconds", 12.0) or 12.0)
        except Exception:
            return 12.0

    def _public_client_id(self) -> str:
        return str(self.settings.get("rd_public_client_id", self.PUBLIC_CLIENT_ID) or self.PUBLIC_CLIENT_ID)

    def _client_id(self) -> str:
        return str(self.settings.get("rd_client_id", self.PUBLIC_CLIENT_ID) or self.PUBLIC_CLIENT_ID)

    def _client_secret(self) -> str:
        return str(self.settings.get("rd_client_secret", "") or "")

    def _access_token(self) -> str:
        return str(self.settings.get("rd_access_token", "") or "")

    def _refresh_token(self) -> str:
        return str(self.settings.get("rd_refresh_token", "") or "")
	    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        return bool(self._access_token())
	    
    def start_device_auth(self) -> Dict[str, str]:
        """
        Start device OAuth flow
        
        Returns:
            dict with device_code, user_code, verification_url, expires_in
        """
        self.event_bus.emit(Events.RD_AUTH_STARTED)
        ctx = get_session()
        ctx_snapshot = SessionContext(
            user_id=ctx.user_id,
            username=ctx.username,
            role=ctx.role or "user",
            profile_id=ctx.profile_id,
        )
	        
        try:
            response = requests.get(
                f"{self.OAUTH_URL}/device/code",
                params={"client_id": self._public_client_id(), "new_credentials": "yes"},
                timeout=self._timeout(),
            )
            response.raise_for_status()
            data = response.json()
            
            # Save device code for polling
            self.settings.set("rd_device_code", data["device_code"])
            
            # Start polling thread
            self._start_polling(
                device_code=data["device_code"],
                interval=int(data.get("interval", 5) or 5),
                expires_in=int(data.get("expires_in", 1800) or 1800),
                ctx_snapshot=ctx_snapshot,
            )
            
            self.event_bus.emit(Events.RD_AUTH_PENDING, data)
            
            return data
        
        except Exception as e:
            self.event_bus.emit(Events.RD_AUTH_FAILED, {"error": str(e)})
            raise
    
    def _start_polling(self, device_code: str, interval: int, expires_in: int, ctx_snapshot: Optional[SessionContext] = None):
        """Start background polling for device authorization"""
        self._stop_polling.clear()
	        
        def poll():
            # Propagate request context to this background thread so settings are
            # written to the correct profile/user scope.
            if ctx_snapshot is not None:
                set_session(ctx_snapshot)
            started = time.time()
            max_wait = max(60, int(expires_in or 1800) + 5)
            while not self._stop_polling.is_set():
                if time.time() - started > max_wait:
                    self.event_bus.emit(Events.RD_AUTH_FAILED, {
                        "error": "Authorization timed out. Please retry."
                    })
                    break
                try:
                    result = self._attempt_device_exchange(device_code)
                    if result.get("status") == "success":
                        self.event_bus.emit(Events.RD_AUTH_SUCCESS, result.get("token_data", {}))
                        break
                    if result.get("status") == "failed":
                        self.event_bus.emit(Events.RD_AUTH_FAILED, {"error": result.get("error", "Authorization failed.")})
                        break
                
                except Exception as e:
                    print(f"Polling error: {e}")
                
                time.sleep(interval)
        
        self._polling_thread = threading.Thread(target=poll, daemon=True)
        self._polling_thread.start()
    
    def stop_polling(self):
        """Stop the polling thread"""
        self._stop_polling.set()

    def check_device_auth_now(self) -> Dict[str, str]:
        """
        One-shot auth check used by UI fallback button.
        Returns dict with status: pending|success|failed and optional message.
        """
        # If polling already completed, surface success immediately.
        if self.is_authenticated():
            try:
                self.get_user_info()
                return {"status": "success", "message": "Authorization verified."}
            except Exception:
                # token exists but invalid; continue normal device check path
                pass

        device_code = (self.settings.get("rd_device_code", "") or "").strip()
        if not device_code:
            return {"status": "failed", "message": "No active device code found. Start authorization again."}
        try:
            result = self._attempt_device_exchange(device_code)
            status = result.get("status", "failed")
            if status == "success":
                self.event_bus.emit(Events.RD_AUTH_SUCCESS, result.get("token_data", {}))
                return {"status": "success", "message": "Authorization verified."}
            if status == "pending":
                return {"status": "pending", "message": result.get("error", "Still waiting for authorization.")}
            self.event_bus.emit(Events.RD_AUTH_FAILED, {"error": result.get("error", "Authorization failed.")})
            return {"status": "failed", "message": result.get("error", "Authorization failed.")}
        except Exception as e:
            return {"status": "failed", "message": str(e)}

    def _attempt_device_exchange(self, device_code: str) -> Dict[str, str]:
        """Try completing device auth once; does not emit events."""
        with self._auth_lock:
            response = requests.get(
                f"{self.OAUTH_URL}/device/credentials",
                params={"client_id": self._public_client_id(), "code": device_code},
                timeout=self._timeout(),
            )

            if response.status_code in (204, 403):
                return {"status": "pending", "error": "Waiting for you to authorize in browser."}
            if response.status_code != 200:
                try:
                    payload = response.json()
                    err = payload.get("error") or payload.get("error_message") or payload.get("error_code")
                except Exception:
                    err = response.text.strip()[:200]
                return {"status": "failed", "error": f"Credentials step failed ({response.status_code}): {err}"}

            cred_data = response.json()
            bound_client_id = cred_data.get("client_id", "")
            bound_client_secret = cred_data.get("client_secret", "")
            if not bound_client_id or not bound_client_secret:
                return {"status": "failed", "error": "RealDebrid did not return client credentials."}

            token_resp = requests.post(
                f"{self.OAUTH_URL}/token",
                data={
                    "client_id": bound_client_id,
                    "client_secret": bound_client_secret,
                    "code": device_code,
                    "grant_type": "http://oauth.net/grant_type/device/1.0",
                },
                timeout=self._timeout(),
            )
            if token_resp.status_code >= 400:
                try:
                    payload = token_resp.json()
                    err = payload.get("error") or payload.get("error_description") or payload.get("error_code")
                except Exception:
                    err = token_resp.text.strip()[:200]
                return {"status": "failed", "error": f"Token exchange failed ({token_resp.status_code}): {err}"}

            token_data = token_resp.json()
            access_token = token_data.get("access_token", "")
            refresh_token = token_data.get("refresh_token", "")
            if not access_token or not refresh_token:
                return {"status": "failed", "error": "Missing access/refresh token in response."}

            self._save_tokens(access_token, refresh_token)
            self.settings.update({
                "rd_client_id": bound_client_id,
                "rd_client_secret": bound_client_secret,
                "rd_device_code": "",
            })
            return {"status": "success", "token_data": token_data}
	    
    def _save_tokens(self, access_token: str, refresh_token: str):
        """Save tokens to settings"""
        self.settings.update({
            "rd_access_token": access_token,
            "rd_refresh_token": refresh_token
        })
    
    def refresh_access_token(self) -> bool:
        """
        Refresh the access token using refresh token
        
        Returns:
            bool indicating success
        """
        refresh_token = self._refresh_token()
        if not refresh_token:
            return False
	        
        try:
            client_secret = self._client_secret()
            client_id = self._client_id()
            if not client_secret:
                return False
            response = requests.post(
                f"{self.OAUTH_URL}/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": refresh_token,
                    "grant_type": "http://oauth.net/grant_type/device/1.0"
                },
                timeout=self._timeout(),
            )
            response.raise_for_status()
            data = response.json()
            
            self._save_tokens(
                data.get("access_token", ""),
                data.get("refresh_token", "")
            )
            
            self.event_bus.emit(Events.RD_TOKEN_REFRESHED)
            return True
        
        except Exception as e:
            print(f"Token refresh failed: {e}")
            return False
    
    def logout(self):
        """Clear authentication"""
        self.settings.update({
            "rd_access_token": "",
            "rd_refresh_token": ""
        })
    
    def _api_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Make authenticated API request with auto token refresh
        """
        access_token = self._access_token()
        if not access_token:
            raise Exception("Not authenticated")
	        
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {access_token}"
        timeout = kwargs.pop("timeout", self._timeout())
	        
        url = f"{self.BASE_URL}/{endpoint}"
        response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
	        
        # Handle token expiration
        if response.status_code == 401:
            if self.refresh_access_token():
                # Retry with new token
                headers["Authorization"] = f"Bearer {self._access_token()}"
                response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
	        
        return response
    
    def resolve_magnet(self, magnet: str, status_callback: Optional[Callable[[str], None]] = None) -> List[str]:
        """
        Resolve magnet link to direct download URLs
        
        Args:
            magnet: Magnet link
        
        Returns:
            List of direct download URLs
        """
        try:
            if status_callback:
                status_callback("Submitting magnet to RealDebrid...")
            # Add magnet to RealDebrid
            response = self._api_request(
                "POST",
                "torrents/addMagnet",
                data={"magnet": magnet}
            )
            response.raise_for_status()
            torrent_data = response.json()
            torrent_id = torrent_data.get("id")
            
            if not torrent_id:
                raise Exception("Failed to add magnet")
            
            if status_callback:
                status_callback("Selecting files...")
            # Select all files
            response = self._api_request(
                "POST",
                f"torrents/selectFiles/{torrent_id}",
                data={"files": "all"}
            )
            response.raise_for_status()

            # Poll for RealDebrid processing and link availability.
            info = self._wait_for_links(torrent_id, status_callback=status_callback)
            links = info.get("links", [])
            if not links:
                raise Exception("No download links available")
            
            # Unrestrict links
            urls = []
            for link in links:
                if status_callback:
                    status_callback("Unrestricting links...")
                response = self._api_request(
                    "POST",
                    "unrestrict/link",
                    data={"link": link}
                )
                response.raise_for_status()
                unrestrict_data = response.json()
                download_url = unrestrict_data.get("download")
                if download_url:
                    urls.append(download_url)
            
            return urls
        
        except Exception as e:
            print(f"Magnet resolution error: {e}")
            raise

    def resolve_torrent_url(self, torrent_url: str, status_callback: Optional[Callable[[str], None]] = None) -> List[str]:
        """
        Resolve a torrent file URL (.torrent or tracker dl endpoint) to direct download URLs.
        """
        try:
            response = requests.get(
                torrent_url,
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            response.raise_for_status()
            content = response.content
            if not content:
                raise Exception("Empty torrent file response")

            if status_callback:
                status_callback("Uploading torrent file to RealDebrid...")
            add_resp = self._api_request(
                "PUT",
                "torrents/addTorrent",
                files={"file": ("upload.torrent", content, "application/x-bittorrent")}
            )
            add_resp.raise_for_status()
            torrent_data = add_resp.json()
            torrent_id = torrent_data.get("id")
            if not torrent_id:
                raise Exception("Failed to add torrent file")

            if status_callback:
                status_callback("Selecting files...")
            select_resp = self._api_request(
                "POST",
                f"torrents/selectFiles/{torrent_id}",
                data={"files": "all"}
            )
            select_resp.raise_for_status()

            info = self._wait_for_links(torrent_id, status_callback=status_callback)
            links = info.get("links", [])
            if not links:
                raise Exception("No links available from torrent")

            out = []
            for link in links:
                if status_callback:
                    status_callback("Unrestricting links...")
                u_resp = self._api_request(
                    "POST",
                    "unrestrict/link",
                    data={"link": link}
                )
                u_resp.raise_for_status()
                direct = u_resp.json().get("download")
                if direct:
                    out.append(direct)
            return out
        except Exception as e:
            print(f"Torrent URL resolution error: {e}")
            raise

    def _wait_for_links(self, torrent_id: str, status_callback: Optional[Callable[[str], None]] = None) -> Dict:
        """
        Poll torrent info until links are available or timeout.
        """
        timeout_seconds = 180
        poll_interval = 2.0
        start = time.time()
        last_status = ""
        while time.time() - start < timeout_seconds:
            response = self._api_request("GET", f"torrents/info/{torrent_id}")
            response.raise_for_status()
            info = response.json()
            status = str(info.get("status", "") or "").strip()
            links = info.get("links", []) or []
            progress = info.get("progress", 0)

            if status != last_status and status_callback:
                status_callback(f"RealDebrid: {status or 'processing'} ({progress}%)")
                last_status = status

            if links:
                return info

            if status in {"error", "magnet_error", "virus", "dead"}:
                raise Exception(f"RealDebrid status: {status}")

            time.sleep(poll_interval)

        raise Exception("Timed out waiting for RealDebrid to prepare links.")

    def list_torrents(self, page: int = 1, limit: int = 100) -> List[Dict]:
        """List user torrents from RealDebrid."""
        response = self._api_request(
            "GET",
            "torrents",
            params={"page": max(1, page), "limit": max(1, min(limit, 500))}
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data
        return []

    def get_torrent_info(self, torrent_id: str) -> Dict:
        """Fetch torrent info by id."""
        response = self._api_request("GET", f"torrents/info/{torrent_id}")
        response.raise_for_status()
        return response.json()

    def check_instant_availability(self, infohash: str) -> bool:
        """
        Check if hash is instantly available on RealDebrid.
        Returns True if at least one host variant is available.
        """
        hash_clean = (infohash or "").strip().lower()
        if not hash_clean:
            return False
        response = self._api_request("GET", f"torrents/instantAvailability/{hash_clean}")
        response.raise_for_status()
        data = response.json()
        # Response keyed by hash, value is dict of hosters when available.
        if not isinstance(data, dict):
            return False
        node = data.get(hash_clean) or data.get(hash_clean.upper()) or {}
        if isinstance(node, dict):
            return any(bool(v) for v in node.values())
        return False
    
    def get_user_info(self) -> Dict:
        """Get user account information"""
        response = self._api_request("GET", "user")
        response.raise_for_status()
        return response.json()
