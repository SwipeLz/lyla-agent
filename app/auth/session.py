from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config import settings


@dataclass
class Session:
    token: str
    username: str
    expires_at: datetime


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, username: str) -> Session:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(tz=timezone.utc) + timedelta(
            hours=settings.session_ttl_hours
        )
        session = Session(token=token, username=username, expires_at=expires_at)
        with self._lock:
            self._sessions[token] = session
        return session

    def get(self, token: str) -> Session | None:
        if not token:
            return None
        now = datetime.now(tz=timezone.utc)
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if session.expires_at <= now:
                self._sessions.pop(token, None)
                return None
            return session

    def revoke(self, token: str) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def cleanup_expired(self) -> int:
        now = datetime.now(tz=timezone.utc)
        with self._lock:
            expired = [t for t, s in self._sessions.items() if s.expires_at <= now]
            for t in expired:
                self._sessions.pop(t, None)
            return len(expired)


session_store = SessionStore()
