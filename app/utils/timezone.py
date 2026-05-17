"""Timezone helpers.

The service layer stores timestamps in UTC. The ``Asia/Jakarta`` window is
only required when computing the user-facing "today" range (e.g. for the
``get_today_summary_tool``). Centralising ``now_utc`` gives tests a single
injection point for monkeypatching the clock.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

JAKARTA = ZoneInfo("Asia/Jakarta")


def now_utc() -> datetime:
    """Return the current instant as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def jakarta_today_window_utc(
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return ``[start_utc, end_utc)`` covering the current Asia/Jakarta day.

    The start aligns with 00:00:00 in Asia/Jakarta of the calendar day that
    contains ``now`` (or ``now_utc()`` when ``now`` is ``None``). The end is
    exactly 24 hours after the start. Both bounds are returned as
    timezone-aware UTC datetimes for direct comparison against UTC columns.
    """
    if now is None:
        now = now_utc()

    jakarta_now = now.astimezone(JAKARTA)
    start_jkt = jakarta_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_jkt = start_jkt + timedelta(hours=24)

    start_utc = start_jkt.astimezone(timezone.utc)
    end_utc = end_jkt.astimezone(timezone.utc)
    return start_utc, end_utc
