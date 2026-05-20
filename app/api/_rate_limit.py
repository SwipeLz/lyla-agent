from __future__ import annotations

import threading
import time

from fastapi import HTTPException, Request

from app.config import settings


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


class LoginRateLimiter:
    def __init__(self) -> None:
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, ip: str, now: float) -> list[float]:
        window = settings.login_rate_limit_window_seconds
        cutoff = now - window
        timestamps = self._failures.get(ip, [])
        recent = [t for t in timestamps if t > cutoff]
        if recent:
            self._failures[ip] = recent
        else:
            self._failures.pop(ip, None)
        return recent

    def check(self, ip: str) -> None:
        now = time.time()
        with self._lock:
            recent = self._prune(ip, now)
            if len(recent) >= settings.login_rate_limit_max_fails:
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed login attempts. Try again later.",
                )

    def record_failure(self, ip: str) -> None:
        now = time.time()
        with self._lock:
            recent = self._prune(ip, now)
            recent.append(now)
            self._failures[ip] = recent

    def record_success(self, ip: str) -> None:
        with self._lock:
            self._failures.pop(ip, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


login_rate_limiter = LoginRateLimiter()
