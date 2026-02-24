"""
RuTracker Search Source
Authenticated tracker search with mirror fallback and explicit auth/captcha failures.
"""
from typing import List, Optional
from urllib.parse import urljoin
import re
import threading

import requests
from bs4 import BeautifulSoup

from ..models.search_result import SearchResult
from .base import BaseSource


class _RuTrackerAuthError(Exception):
    pass


class _RuTrackerCaptchaRequired(Exception):
    pass


class RuTrackerSource(BaseSource):
    """RuTracker source (opt-in, credentialed)."""

    name = "RuTracker"
    MIRRORS = [
        "https://rutracker.org",
        "https://rutracker.net",
        "https://rutracker.nl",
    ]

    def __init__(self, settings):
        self.settings = settings
        self.base_url = self.MIRRORS[0]
        self.last_error = ""
        self._logged_in = False
        self._lock = threading.RLock()

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        })

    def search(self, query: str, page: int = 1) -> List[SearchResult]:
        self.last_error = ""
        if not self.settings.get("rutracker_enabled", False):
            return []

        username = (self.settings.get("rutracker_username", "") or "").strip()
        password = (self.settings.get("rutracker_password", "") or "").strip()
        if not username or not password:
            self.last_error = "RuTracker is enabled but username/password are missing."
            return []

        with self._lock:
            if not self._ensure_logged_in(username, password):
                return []

        results = self._search_tracker(query, page)
        if results:
            return results

        # Session may have expired; relog once and retry.
        with self._lock:
            self._logged_in = False
            if self._ensure_logged_in(username, password):
                return self._search_tracker(query, page)
        return []

    def _ensure_logged_in(self, username: str, password: str) -> bool:
        if self._logged_in and self._has_session_cookie():
            return True

        mirror_order = [self.base_url] + [m for m in self.MIRRORS if m != self.base_url]
        last_error: Optional[str] = None

        for mirror in mirror_order:
            try:
                self._login_on_mirror(mirror, username, password)
                self.base_url = mirror
                self._logged_in = True
                self.last_error = ""
                return True
            except _RuTrackerCaptchaRequired as e:
                self._logged_in = False
                self.last_error = str(e)
                return False
            except Exception as e:
                last_error = str(e)
                continue

        self._logged_in = False
        self.last_error = f"RuTracker login failed on all mirrors. {last_error or ''}".strip()
        return False

    def _login_on_mirror(self, mirror: str, username: str, password: str):
        login_page_url = f"{mirror}/forum/login.php?redirect=tracker.php"
        response = self.session.get(login_page_url, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        form = self._find_login_form(soup)
        if form is None:
            raise _RuTrackerAuthError("Login form not found.")

        action = form.get("action") or "login.php"
        post_url = urljoin(login_page_url, action)
        payload = self._collect_form_payload(form)
        payload["login_username"] = username
        payload["login_password"] = password
        payload["login"] = payload.get("login", "Вход")

        post_response = self.session.post(post_url, data=payload, timeout=20, allow_redirects=True)
        post_response.raise_for_status()
        post_soup = BeautifulSoup(post_response.content, "html.parser")

        if self._response_has_captcha(post_soup, post_response.text):
            raise _RuTrackerCaptchaRequired(
                "RuTracker requires captcha after login attempts. Open rutracker in browser and verify credentials."
            )

        if self._has_session_cookie():
            return

        auth_msg = self._extract_auth_error(post_soup, post_response.text)
        raise _RuTrackerAuthError(auth_msg or "Invalid credentials or login blocked.")

    def _has_session_cookie(self) -> bool:
        return any(cookie.name == "bb_session" for cookie in self.session.cookies)

    def _find_login_form(self, soup: BeautifulSoup):
        for form in soup.find_all("form"):
            names = {i.get("name", "") for i in form.find_all("input")}
            if "login_username" in names and "login_password" in names:
                return form
        return None

    def _collect_form_payload(self, form) -> dict:
        payload = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue
            input_type = (inp.get("type") or "text").lower()
            if input_type in {"submit", "button", "image"}:
                if name == "login":
                    payload[name] = inp.get("value", "Вход")
                continue
            payload[name] = inp.get("value", "")
        return payload

    def _response_has_captcha(self, soup: BeautifulSoup, raw_text: str) -> bool:
        low = raw_text.lower()
        if "captcha" in low or "капча" in low:
            return True
        if soup.find("input", {"name": "cap_sid"}) or soup.find("input", {"name": "cap_code"}):
            return True
        if soup.find("img", src=re.compile(r"captcha", re.IGNORECASE)):
            return True
        return False

    def _extract_auth_error(self, soup: BeautifulSoup, raw_text: str) -> str:
        warn = soup.select_one(".warnColor1")
        if warn:
            return warn.get_text(" ", strip=True)
        # Fallback on common fragments
        low = raw_text.lower()
        if "неверное" in low or "неверный пароль" in low:
            return "Invalid RuTracker username/password."
        if "access denied" in low or "forbidden" in low:
            return "RuTracker denied access."
        return ""

    def _search_tracker(self, query: str, page: int = 1) -> List[SearchResult]:
        start = max(0, (page - 1) * 50)
        url = f"{self.base_url}/forum/tracker.php"
        response = self.session.get(url, params={"nm": query, "start": start}, timeout=25, allow_redirects=True)
        response.raise_for_status()

        # If redirected back to login, auth is no longer valid.
        if "login.php" in response.url:
            self.last_error = "RuTracker session expired; please retry."
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        rows = soup.select("tr[id^='trs-tr-']")
        results: List[SearchResult] = []

        for row in rows:
            result = self._parse_row(row)
            if result:
                results.append(result)

        if not rows and not results:
            txt = soup.get_text(" ", strip=True).lower()
            if "ничего не найдено" in txt or "no matches" in txt:
                return []
            if self._response_has_captcha(soup, response.text):
                self.last_error = "RuTracker search is blocked by captcha."

        return results

    def _parse_row(self, row) -> Optional[SearchResult]:
        topic_link = row.select_one("a[data-topic_id]") or row.select_one("a[href*='viewtopic.php?t=']")
        if not topic_link:
            return None

        topic_id = topic_link.get("data-topic_id") or self._extract_topic_id(topic_link.get("href", ""))
        if not topic_id:
            return None

        title = topic_link.get_text(" ", strip=True)
        if not title:
            return None

        size_bytes = 0
        seeds = 0
        leeches = 0

        # RuTracker rows expose sortable values in data-ts_text attributes.
        ts_values = []
        for node in row.find_all(attrs={"data-ts_text": True}):
            raw = (node.get("data-ts_text") or "").strip()
            if re.fullmatch(r"-?\d+", raw):
                ts_values.append(int(raw))
        if ts_values:
            # Usually: size, seeds, timestamp
            size_bytes = max((v for v in ts_values if v > 1024), default=0)
            seeds = max((v for v in ts_values if 0 <= v < 10000000), default=0)

        leech_node = row.select_one(".leechmed") or row.select_one("td.leechmed")
        if leech_node:
            txt = re.sub(r"[^\d]", "", leech_node.get_text(" ", strip=True))
            if txt.isdigit():
                leeches = int(txt)

        download_url = f"{self.base_url}/forum/dl.php?t={topic_id}"
        return SearchResult(
            title=title,
            magnet=download_url,
            size=size_bytes,
            seeds=max(seeds, 0),
            leeches=max(leeches, 0),
            source=self.name,
            infohash="",  # Not available without fetching torrent/magnet.
        )

    def _extract_topic_id(self, href: str) -> str:
        match = re.search(r"[?&]t=(\d+)", href or "")
        return match.group(1) if match else ""
