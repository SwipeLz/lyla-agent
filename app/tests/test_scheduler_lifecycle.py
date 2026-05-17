"""Integration test for the FastAPI lifespan gating of the Reminder
Scheduler.

Covers Property RS1 from
``.kiro/specs/agent-runtime-and-apis/design.md`` (Correctness Properties →
Reminder Scheduler).

**Property RS1: Lifecycle gating**

Using ``with TestClient(app):`` to drive the FastAPI lifespan startup
and shutdown events:

- When ``settings.scheduler_enabled`` is ``True`` on startup, the
  application SHALL construct a ``BackgroundScheduler``, store it on
  ``app.state.scheduler``, and start it (``scheduler.running is True``).
- When ``settings.scheduler_enabled`` is ``False`` on startup, no
  scheduler SHALL be constructed (``app.state.scheduler is None``).
- After the lifespan shutdown event runs (i.e. after the
  ``with TestClient(app):`` block exits), the scheduler that was
  started SHALL no longer be running (``scheduler.running is False``).

**Validates: Requirements 7.5, 7.6, 7.7**
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def _reset_scheduler_state():
    """Ensure no stale ``app.state.scheduler`` leaks between tests.

    The FastAPI ``app`` object is module-scoped, so tests in this file
    share state through ``app.state``. Reset before and after each
    test so the assertions reflect only what *this* lifespan run did.
    """
    if hasattr(app.state, "scheduler"):
        delattr(app.state, "scheduler")
    yield
    sched = getattr(app.state, "scheduler", None)
    if sched is not None and getattr(sched, "running", False):
        # Defensive: if a test forgot to exit the TestClient context,
        # tear down the scheduler so subsequent tests start clean.
        sched.shutdown(wait=False)
    if hasattr(app.state, "scheduler"):
        delattr(app.state, "scheduler")


# ── Property RS1 case A: scheduler_enabled=True ────────────────────


def test_lifespan_starts_scheduler_when_enabled(monkeypatch):
    """With ``scheduler_enabled=True``, lifespan startup creates a
    running scheduler on ``app.state.scheduler``; lifespan shutdown
    stops it.

    Validates: Requirements 7.5, 7.7
    """
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    # Use a long interval so the first tick will not fire while the
    # ``with`` block is open. APScheduler's interval trigger schedules
    # the first run ``interval`` seconds after start, but we keep this
    # high to make the test robust against future trigger changes and
    # to avoid hitting ``SessionLocal`` against the on-disk database.
    monkeypatch.setattr(settings, "scheduler_interval_seconds", 3600)

    captured_scheduler = None
    with TestClient(app) as _client:
        # Lifespan startup has run. Scheduler must be constructed and
        # running per Req 7.5.
        scheduler = getattr(app.state, "scheduler", None)
        assert scheduler is not None, (
            "app.state.scheduler must be set when scheduler_enabled=True"
        )
        assert scheduler.running is True, (
            "BackgroundScheduler.running must be True after startup"
        )
        captured_scheduler = scheduler

    # Lifespan shutdown has run. The captured scheduler must no longer
    # be running per Req 7.7.
    assert captured_scheduler is not None
    assert captured_scheduler.running is False, (
        "BackgroundScheduler.running must be False after lifespan shutdown"
    )


# ── Property RS1 case B: scheduler_enabled=False ───────────────────


def test_lifespan_does_not_start_scheduler_when_disabled(monkeypatch):
    """With ``scheduler_enabled=False``, lifespan startup must NOT
    construct a scheduler; ``app.state.scheduler`` stays ``None``.

    Validates: Requirement 7.6
    """
    monkeypatch.setattr(settings, "scheduler_enabled", False)

    with TestClient(app) as _client:
        # Lifespan startup has run. With the gate off, no scheduler
        # should have been created.
        scheduler = getattr(app.state, "scheduler", None)
        assert scheduler is None, (
            "app.state.scheduler must be None when scheduler_enabled=False, "
            f"got {scheduler!r}"
        )
