"""Reminder Scheduler lifecycle helpers.

Wraps APScheduler's `BackgroundScheduler` so the FastAPI lifespan can start
it on application startup (gated by `settings.scheduler_enabled`) and stop
it on shutdown without leaking thread state.

Public API:

- ``start_scheduler(app)`` — construct a `BackgroundScheduler`, register the
  `reminder_tick` job at `settings.scheduler_interval_seconds`, start the
  scheduler, and return it. The caller is expected to store the returned
  instance on ``app.state.scheduler`` so ``stop_scheduler`` can find it.
- ``stop_scheduler(app)`` — defensively read ``app.state.scheduler`` and
  call ``shutdown(wait=False)`` if a scheduler is present. Never raises.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.db import SessionLocal
from app.scheduler.tick import reminder_tick

if TYPE_CHECKING:  # pragma: no cover - typing-only import
    from fastapi import FastAPI


def _run_reminder_tick() -> None:
    """Job callable bound to APScheduler.

    Wraps `reminder_tick(db_factory=SessionLocal)` so the scheduler can
    invoke it without needing access to the request-scoped DB dependency.
    Return value is discarded; the tick reports counters via its return
    value but APScheduler does not use them.
    """
    reminder_tick(db_factory=SessionLocal)


def start_scheduler(app: "FastAPI") -> BackgroundScheduler:
    """Create, configure, and start the Reminder Scheduler.

    Args:
        app: The FastAPI application instance. Currently unused inside this
            function but accepted so callers can pass the app for future
            wiring (e.g. attaching app-level state) without changing the
            signature.

    Returns:
        The started `BackgroundScheduler` instance. Callers should store
        the returned scheduler on ``app.state.scheduler`` so
        ``stop_scheduler`` can shut it down later.
    """
    scheduler = BackgroundScheduler(timezone=ZoneInfo("UTC"))
    scheduler.add_job(
        func=_run_reminder_tick,
        trigger="interval",
        seconds=settings.scheduler_interval_seconds,
        id="reminder_tick",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler


def stop_scheduler(app: "FastAPI") -> None:
    """Shut down the Reminder Scheduler if one was started.

    Reads ``app.state.scheduler`` defensively: if the attribute is missing
    or ``None``, this is a no-op. Otherwise, the scheduler is shut down
    with ``wait=False`` so application shutdown is not blocked by an
    in-flight tick.
    """
    scheduler: Optional[BackgroundScheduler] = getattr(
        app.state, "scheduler", None
    )
    if scheduler is None:
        return
    scheduler.shutdown(wait=False)
