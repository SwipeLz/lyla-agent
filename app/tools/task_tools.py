"""Task tool wrappers.

Plain Python wrappers around ``app.services.task_service``. These are *not*
Google ADK tool objects; they are thin adapters that translate service-layer
exceptions into the agent-facing **Tool Result Dict** contract.

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

from app.services import task_service
from app.services.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


def create_task_tool(
    db,
    user_id,
    title,
    course=None,
    deadline_at=None,
    reminder_at=None,
    priority=None,
) -> dict:
    """Wrap :func:`task_service.create_task` into a Tool Result Dict."""
    try:
        task = task_service.create_task(
            db,
            user_id=user_id,
            title=title,
            course=course,
            deadline_at=deadline_at,
            reminder_at=reminder_at,
            priority=priority,
        )
    except (ValidationError, NotFoundError, PermissionDeniedError) as e:
        return {"success": False, "type": "task", "error": str(e)}
    return {
        "success": True,
        "type": "task",
        "id": task.id,
        "message": "Tugas berhasil dicatat.",
    }
