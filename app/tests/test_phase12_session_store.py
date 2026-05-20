from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.auth.session import Session, SessionStore


def test_create_returns_43_char_url_safe_token():
    store = SessionStore()
    s = store.create("admin")
    assert isinstance(s, Session)
    assert s.username == "admin"
    assert len(s.token) == 43
    allowed = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    )
    assert set(s.token) <= allowed


def test_get_returns_same_session():
    store = SessionStore()
    s = store.create("admin")
    fetched = store.get(s.token)
    assert fetched is not None
    assert fetched.token == s.token
    assert fetched.username == "admin"


def test_revoke_removes_session():
    store = SessionStore()
    s = store.create("admin")
    store.revoke(s.token)
    assert store.get(s.token) is None


def test_get_returns_none_for_unknown_token():
    store = SessionStore()
    assert store.get("nonexistent") is None
    assert store.get("") is None


def test_expired_session_is_lazy_evicted():
    store = SessionStore()
    s = store.create("admin")
    s.expires_at = datetime.now(tz=timezone.utc) - timedelta(seconds=1)
    assert store.get(s.token) is None
    assert store.get(s.token) is None


def test_cleanup_expired_returns_count():
    store = SessionStore()
    a = store.create("admin")
    b = store.create("admin")
    a.expires_at = datetime.now(tz=timezone.utc) - timedelta(seconds=1)
    removed = store.cleanup_expired()
    assert removed == 1
    assert store.get(a.token) is None
    assert store.get(b.token) is not None
