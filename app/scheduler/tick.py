"""Reminder Scheduler tick.

`reminder_tick` is a pure function that performs one Scheduler Tick:

1. Open a DB session via the supplied `db_factory`.
2. Fetch all Due Reminders via `reminder_service.list_due_reminders`.
3. For each reminder, route by `channel`:
   - `"device"` or `"both"` → resolve the user's first `Device` and call
     `device_service.queue_device_command(...)`.
   - `"whatsapp"` or `"both"` → call the injected `whatsapp_send`.
4. If every dispatch call returns without raising, transition the reminder
   to ``SENT`` via `reminder_service.mark_reminder_sent`.
5. If any dispatch call raises, catch the exception, transition the
   reminder to ``FAILED`` via `reminder_service.mark_reminder_failed`, and
   continue with the next Due Reminder within the same tick.
6. Special case (Req 8.7): when `channel == "device"` and the user has no
   associated `Device`, skip dispatch entirely and DO NOT transition the
   reminder's status. For `channel == "both"` with no device, skip the
   device dispatch but still attempt the WhatsApp leg.

Returns a counter dict: ``{"sent": int, "failed": int, "skipped": int}``.

This function intentionally takes a `db_factory` (not a `Session`) so the
APScheduler job and tests can both call it without sharing session state.
"""

from __future__ import annotations

from typing import Callable, Optional

from app.models.device import Device
from app.services import device_service, reminder_service


def reminder_tick(
    *,
    db_factory: Callable,
    whatsapp_send: Optional[Callable] = None,
) -> dict:
    """Run one Scheduler Tick and return a counter dict.

    Args:
        db_factory: Zero-argument callable that returns a fresh SQLAlchemy
            ``Session``. Typically `app.db.SessionLocal`.
        whatsapp_send: Optional callable accepting a ``Reminder`` and
            returning any value (return value is ignored). Defaults to
            ``app.integrations.whatsapp.whatsapp_send_stub``.

    Returns:
        ``{"sent": <int>, "failed": <int>, "skipped": <int>}``.
    """
    if whatsapp_send is None:
        # Lazy import keeps `app.scheduler` cheap to import.
        from app.integrations.whatsapp import whatsapp_send_stub

        whatsapp_send = whatsapp_send_stub

    sent = 0
    failed = 0
    skipped = 0

    db = db_factory()
    try:
        due = reminder_service.list_due_reminders(db)
        for reminder in due:
            try:
                channel = reminder.channel

                # Device dispatch leg.
                if channel in ("device", "both"):
                    user_devices = (
                        db.query(Device)
                        .filter(Device.user_id == reminder.user_id)
                        .all()
                    )
                    if user_devices:
                        device_service.queue_device_command(
                            db,
                            user_devices[0].id,
                            command_type="show_text",
                            payload={"text": reminder.title},
                        )
                    elif channel == "device":
                        # Req 8.7: device-only reminder with no device → skip
                        # dispatch and do not transition the reminder status.
                        skipped += 1
                        continue
                    # else channel == "both" without a device: fall through
                    # to the WhatsApp leg.

                # WhatsApp dispatch leg.
                if channel in ("whatsapp", "both"):
                    whatsapp_send(reminder)

                reminder_service.mark_reminder_sent(db, reminder.id)
                sent += 1
            except Exception:
                # Req 8.5: catch and continue with remaining reminders.
                reminder_service.mark_reminder_failed(db, reminder.id)
                failed += 1
    finally:
        db.close()

    return {"sent": sent, "failed": failed, "skipped": skipped}
