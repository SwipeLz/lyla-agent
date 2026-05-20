from __future__ import annotations

from fastapi import HTTPException

from app.api._rate_limit import LoginRateLimiter
from app.config import settings


def test_check_passes_below_threshold():
    limiter = LoginRateLimiter()
    ip = "10.0.0.1"
    for _ in range(settings.login_rate_limit_max_fails - 1):
        limiter.record_failure(ip)
    limiter.check(ip)


def test_check_raises_429_at_threshold():
    limiter = LoginRateLimiter()
    ip = "10.0.0.2"
    for _ in range(settings.login_rate_limit_max_fails):
        limiter.record_failure(ip)
    try:
        limiter.check(ip)
    except HTTPException as exc:
        assert exc.status_code == 429
    else:
        raise AssertionError("expected HTTPException 429")


def test_record_success_resets_counter():
    limiter = LoginRateLimiter()
    ip = "10.0.0.3"
    for _ in range(settings.login_rate_limit_max_fails):
        limiter.record_failure(ip)
    limiter.record_success(ip)
    limiter.check(ip)


def test_separate_ips_have_independent_buckets():
    limiter = LoginRateLimiter()
    a, b = "10.0.0.4", "10.0.0.5"
    for _ in range(settings.login_rate_limit_max_fails):
        limiter.record_failure(a)
    limiter.check(b)


def test_old_failures_outside_window_are_pruned(monkeypatch):
    limiter = LoginRateLimiter()
    ip = "10.0.0.6"
    fake_now = [1000.0]
    monkeypatch.setattr("app.api._rate_limit.time.time", lambda: fake_now[0])
    for _ in range(settings.login_rate_limit_max_fails):
        limiter.record_failure(ip)
    fake_now[0] += settings.login_rate_limit_window_seconds + 1
    limiter.check(ip)
