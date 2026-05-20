"""Shared pytest fixtures.

Every test using the database must depend on the ``db_session`` fixture
defined here. The fixture builds a fresh ``sqlite:///:memory:`` engine per
test function with foreign keys enabled, so tests are fully isolated and
the on-disk ``taskbot.db`` file is never touched.

This module also installs an autouse network kill-switch fixture that
blocks any outbound socket connection to non-loopback hosts. This
enforces:

- Property AR6 (Fake Agent Hermeticity)
- Property RS5 (No real WhatsApp call)
- Property X1  (No real Gemini call in default tests)

**Validates: Requirements 3.5, 8.6, 16.2, 16.3**
"""
from __future__ import annotations

import socket as _socket

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base

# Importing the models package registers all tables on ``Base.metadata``.
import app.models  # noqa: F401


# ---------------------------------------------------------------------------
# Network kill-switch
# ---------------------------------------------------------------------------

# Loopback hosts that remain reachable during tests. FastAPI's TestClient
# uses an in-memory ASGI transport (no real sockets), but some libraries
# may still resolve or connect to ``127.0.0.1``/``localhost`` for legitimate
# in-process work — keep that path open.
_LOOPBACK_HOSTS: frozenset[str] = frozenset(
    {"127.0.0.1", "::1", "localhost", "0.0.0.0"}
)


def _is_loopback_address(address: object) -> bool:
    """Return True when ``address`` targets a loopback host."""
    if not isinstance(address, tuple) or not address:
        return False
    host = address[0]
    if not isinstance(host, str):
        return False
    return host in _LOOPBACK_HOSTS


@pytest.fixture(autouse=True)
def _no_outbound_network(monkeypatch):
    """Block outbound network connections during the default test run.

    Patches ``socket.socket.connect``/``connect_ex``,
    ``socket.create_connection`` and ``socket.getaddrinfo`` so that only
    loopback destinations resolve or connect. Any attempt to reach an
    external host raises ``RuntimeError`` with a clear message, ensuring
    accidental HTTP calls (real Gemini, WhatsApp Cloud API, etc.) fail
    loudly instead of silently leaving the test sandbox.

    **Validates: Requirements 3.5, 8.6, 16.2, 16.3**
    """
    real_connect = _socket.socket.connect
    real_connect_ex = _socket.socket.connect_ex
    real_create_connection = _socket.create_connection
    real_getaddrinfo = _socket.getaddrinfo

    def guarded_connect(self, address):
        if _is_loopback_address(address):
            return real_connect(self, address)
        raise RuntimeError(
            f"Outbound network blocked in tests "
            f"(socket.connect to {address!r})"
        )

    def guarded_connect_ex(self, address):
        if _is_loopback_address(address):
            return real_connect_ex(self, address)
        raise RuntimeError(
            f"Outbound network blocked in tests "
            f"(socket.connect_ex to {address!r})"
        )

    def guarded_create_connection(address, *args, **kwargs):
        if _is_loopback_address(address):
            return real_create_connection(address, *args, **kwargs)
        raise RuntimeError(
            f"Outbound network blocked in tests "
            f"(socket.create_connection to {address!r})"
        )

    def guarded_getaddrinfo(host, *args, **kwargs):
        # ``host`` may be ``None`` (passive lookup) — allow it.
        if host is None or host in _LOOPBACK_HOSTS:
            return real_getaddrinfo(host, *args, **kwargs)
        raise RuntimeError(
            f"Outbound DNS blocked in tests "
            f"(socket.getaddrinfo for {host!r})"
        )

    monkeypatch.setattr(_socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(_socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(_socket, "create_connection", guarded_create_connection)
    monkeypatch.setattr(_socket, "getaddrinfo", guarded_getaddrinfo)

    yield


@pytest.fixture(autouse=True)
def _disable_device_token_gate_by_default(monkeypatch):
    """Default tests run with REQUIRE_DEVICE_TOKEN=False.

    Production default is True. Each test that wants to exercise the
    gate explicitly opts in via ``monkeypatch.setattr(settings,
    "require_device_token", True)``. Without this autouse fixture, the
    256 pre-Phase-12 audio tests would all need to be retrofitted with
    a paired Device + ``X-Device-Token`` header.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "require_device_token", False)
    yield


# ---------------------------------------------------------------------------
# Database session fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
