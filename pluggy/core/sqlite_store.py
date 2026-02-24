"""
SQLite-backed store for users, sessions, profiles, and profile-scoped settings.

Design goals:
- Local-first (works in contained app and on a server).
- No external Python dependencies (uses stdlib sqlite3 + PBKDF2).
- Profile-scoped settings are stored as one JSON blob per profile.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import hmac


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(ts: str) -> float:
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        return 0.0


def _pbkdf2_hash(password: str, salt: bytes, iters: int = 150_000) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iters = 150_000
    digest = _pbkdf2_hash(password, salt, iters)
    return f"pbkdf2_sha256${iters}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iters_s, salt_hex, digest_hex = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        got = _pbkdf2_hash(password, salt, int(iters_s))
        return hmac.compare_digest(expected, got)
    except Exception:
        return False


@dataclass(frozen=True)
class UserRow:
    id: int
    username: str
    role: str


@dataclass(frozen=True)
class ProfileRow:
    id: str
    user_id: int
    name: str
    avatar: str
    theme_id: str


class SqliteStore:
    def __init__(self, data_dir: Path):
        self._lock = RLock()
        self._db_path = Path(data_dir) / "pluggy.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
        self._migrate()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def reset_local_data(self) -> None:
        """Remove user/profile/session/settings rows while keeping schema intact."""
        with self._lock, self._conn:
            # Child tables first to avoid FK issues.
            for table in ("sessions", "profile_settings", "user_settings", "profiles", "users"):
                self._conn.execute(f"DELETE FROM {table}")
            try:
                self._conn.execute(
                    "DELETE FROM sqlite_sequence WHERE name IN ('users')"
                )
            except Exception:
                # sqlite_sequence may not exist yet if AUTOINCREMENT was never used.
                pass

    def _migrate(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
            )
            row = self._conn.execute("SELECT version FROM schema_version").fetchone()
            if not row:
                self._conn.execute("INSERT INTO schema_version(version) VALUES (1)")

            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password_hash TEXT NOT NULL,
                  role TEXT NOT NULL DEFAULT 'user',
                  created_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                  id TEXT PRIMARY KEY,
                  user_id INTEGER NOT NULL,
                  name TEXT NOT NULL,
                  avatar TEXT NOT NULL DEFAULT '',
                  theme_id TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                  token TEXT PRIMARY KEY,
                  user_id INTEGER NOT NULL,
                  profile_id TEXT,
                  created_at TEXT NOT NULL,
                  expires_at TEXT NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                  FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE SET NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS profile_settings (
                  profile_id TEXT PRIMARY KEY,
                  settings_json TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_settings (
                  user_id INTEGER PRIMARY KEY,
                  settings_json TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )

    # ---- Users ----
    def count_users(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(1) AS n FROM users").fetchone()
            return int(row["n"] if row else 0)

    def create_user(self, username: str, password: str, role: str = "user") -> UserRow:
        normalized = (username or "").strip().lower()
        if not normalized:
            raise ValueError("username is required")
        if not password:
            raise ValueError("password is required")
        safe_role = "admin" if role == "admin" else "user"
        pw_hash = hash_password(password)
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO users(username,password_hash,role,created_at) VALUES (?,?,?,?)",
                (normalized, pw_hash, safe_role, _utc_now_iso()),
            )
            user_id = int(cur.lastrowid)
        return UserRow(id=user_id, username=normalized, role=safe_role)

    def authenticate(self, username: str, password: str) -> Optional[UserRow]:
        normalized = (username or "").strip().lower()
        if not normalized or not password:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT id, username, role, password_hash FROM users WHERE username = ?",
                (normalized,),
            ).fetchone()
        if not row:
            return None
        if not verify_password(password, str(row["password_hash"])):
            return None
        return UserRow(id=int(row["id"]), username=str(row["username"]), role=str(row["role"] or "user"))

    # ---- Sessions ----
    def create_session(self, user_id: int, ttl_seconds: int = 60 * 60 * 24 * 7) -> str:
        token = secrets.token_urlsafe(32)
        now = _utc_now_iso()
        exp = datetime.fromtimestamp(time.time() + int(ttl_seconds), tz=timezone.utc).isoformat().replace("+00:00", "Z")
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO sessions(token,user_id,profile_id,created_at,expires_at) VALUES (?,?,?,?,?)",
                (token, int(user_id), None, now, exp),
            )
        return token

    def delete_session(self, token: str) -> None:
        if not token:
            return
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def get_session(self, token: str) -> Optional[Tuple[UserRow, Optional[str]]]:
        if not token:
            return None
        with self._lock:
            row = self._conn.execute(
                """
                SELECT s.token, s.profile_id, s.expires_at, u.id as user_id, u.username, u.role
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = ?
                """,
                (token,),
            ).fetchone()
        if not row:
            return None
        if _parse_iso(str(row["expires_at"])) < time.time():
            self.delete_session(token)
            return None
        user = UserRow(id=int(row["user_id"]), username=str(row["username"]), role=str(row["role"] or "user"))
        profile_id = str(row["profile_id"]) if row["profile_id"] else None
        return user, profile_id

    def set_session_profile(self, token: str, profile_id: Optional[str]) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE sessions SET profile_id = ? WHERE token = ?", (profile_id, token))

    # ---- Profiles ----
    def list_profiles(self, user_id: int) -> List[ProfileRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, user_id, name, avatar, theme_id FROM profiles WHERE user_id = ? ORDER BY created_at ASC",
                (int(user_id),),
            ).fetchall()
        out: List[ProfileRow] = []
        for r in rows:
            out.append(
                ProfileRow(
                    id=str(r["id"]),
                    user_id=int(r["user_id"]),
                    name=str(r["name"]),
                    avatar=str(r["avatar"] or ""),
                    theme_id=str(r["theme_id"] or ""),
                )
            )
        return out

    def create_profile(self, user_id: int, name: str) -> ProfileRow:
        existing = self.list_profiles(user_id)
        if len(existing) >= 8:
            raise ValueError("Profile limit reached (8).")
        safe_name = (name or "").strip() or f"Profile {len(existing) + 1}"
        profile_id = f"pf_{secrets.token_hex(8)}"
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO profiles(id,user_id,name,avatar,theme_id,created_at) VALUES (?,?,?,?,?,?)",
                (profile_id, int(user_id), safe_name, "", "", _utc_now_iso()),
            )
        return ProfileRow(id=profile_id, user_id=int(user_id), name=safe_name, avatar="", theme_id="")

    def get_profile(self, profile_id: str) -> Optional[ProfileRow]:
        if not profile_id:
            return None
        with self._lock:
            r = self._conn.execute(
                "SELECT id, user_id, name, avatar, theme_id FROM profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        if not r:
            return None
        return ProfileRow(
            id=str(r["id"]),
            user_id=int(r["user_id"]),
            name=str(r["name"]),
            avatar=str(r["avatar"] or ""),
            theme_id=str(r["theme_id"] or ""),
        )

    def set_profile_theme(self, profile_id: str, theme_id: str) -> None:
        if not profile_id:
            return
        safe = (theme_id or "").strip()
        with self._lock, self._conn:
            self._conn.execute("UPDATE profiles SET theme_id = ? WHERE id = ?", (safe, profile_id))

    def update_profile(self, profile_id: str, *, name: Optional[str] = None, avatar: Optional[str] = None, theme_id: Optional[str] = None) -> None:
        if not profile_id:
            return
        sets = []
        values: List[Any] = []
        if name is not None:
            sets.append("name = ?")
            values.append(str(name))
        if avatar is not None:
            sets.append("avatar = ?")
            values.append(str(avatar))
        if theme_id is not None:
            sets.append("theme_id = ?")
            values.append(str(theme_id))
        if not sets:
            return
        values.append(profile_id)
        with self._lock, self._conn:
            self._conn.execute(f"UPDATE profiles SET {', '.join(sets)} WHERE id = ?", tuple(values))

    def delete_profile(self, profile_id: str) -> None:
        if not profile_id:
            return
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))

    # ---- Profile/User Settings ----
    def get_profile_settings(self, profile_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            r = self._conn.execute(
                "SELECT settings_json FROM profile_settings WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
        if not r:
            return None
        try:
            return json.loads(str(r["settings_json"]))
        except Exception:
            return None

    def set_profile_settings(self, profile_id: str, settings: Dict[str, Any]) -> None:
        payload = json.dumps(settings, sort_keys=True)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO profile_settings(profile_id,settings_json,updated_at)
                VALUES (?,?,?)
                ON CONFLICT(profile_id) DO UPDATE SET settings_json=excluded.settings_json, updated_at=excluded.updated_at
                """,
                (profile_id, payload, _utc_now_iso()),
            )

    def get_user_settings(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            r = self._conn.execute(
                "SELECT settings_json FROM user_settings WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
        if not r:
            return None
        try:
            return json.loads(str(r["settings_json"]))
        except Exception:
            return None

    def set_user_settings(self, user_id: int, settings: Dict[str, Any]) -> None:
        payload = json.dumps(settings, sort_keys=True)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO user_settings(user_id,settings_json,updated_at)
                VALUES (?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET settings_json=excluded.settings_json, updated_at=excluded.updated_at
                """,
                (int(user_id), payload, _utc_now_iso()),
            )
