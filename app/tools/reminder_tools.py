"""Reminder tool wrappers.

Plain Python wrappers around ``app.services.reminder_service``. These are
*not* Google ADK tool objects; they are thin adapters that translate
service-layer exceptions into the agent-facing **Tool Result Dict** contract.

Behavior:

- Catches **only** :class:`~app.services.exceptions.ValidationError`,
  :class:`~app.services.exceptions.NotFoundError`, and
  :class:`~app.services.exceptions.PermissionDeniedError`. Any other
  exception (e.g. ``IntegrityError``, programming bugs) is allowed to
  propagate so the agent runtime can surface or log it.
- Returns a Tool Result Dict on both success and handled-failure paths:

  - Success: ``{"success": True, "type": <kind>, "id": <entity_id>,
    "message": <user-facing string>}``
  - Failure: ``{"success": False, "type": <kind>, "error": <str(exc)>}``
"""
from __future__ import annotations

from app.services import reminder_service
from app.services.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


def set_reminder_tool(
    db,
    user_id,
    title,
    remind_at,
    channel="both",
    task_id=None,
) -> dict:
    """Wrap :func:`reminder_service.create_reminder` into a Tool Result Dict."""
    try:
        reminder = reminder_service.create_reminder(
            db,
            user_id=user_id,
            title=title,
            remind_at=remind_at,
            channel=channel,
            task_id=task_id,
        )
    except (ValidationError, NotFoundError, PermissionDeniedError) as e:
        return {"success": False, "type": "reminder", "error": str(e)}
    return {
        "success": True,
        "type": "reminder",
        "id": reminder.id,
        "message": "Reminder berhasil dijadwalkan.",
    }
