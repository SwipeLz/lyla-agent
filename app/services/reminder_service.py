"""Reminder service: business logic for scheduled reminders.

All functions take a SQLAlchemy ``Session`` and primitive/Python objects.
They never depend on FastAPI, agent frameworks, or formatting concerns.

Validation order for ``create_reminder`` (per design):
    1. user exists
    2. title is non-blank
    3. ``remind_at`` is an aware datetime
    4. ``remind_at`` is not earlier than UTC Now
    5. ``channel`` is in ``ALLOWED_CHANNELS``
    6. when ``task_id`` is supplied, the task exists and belongs to user

Lifecycle helpers ``mark_reminder_sent`` and ``mark_reminder_failed`` raise
``NotFoundError`` when the reminder does not exist; otherwise they update
the status and commit.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.constants import ReminderStatus
from app.models.reminder import Reminder
from app.models.task import Task
from app.models.user import User
from app.services.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.utils.timezone import now_utc


ALLOWED_CHANNELS = ("whatsapp", "device", "both")


def _is_aware(dt: datetime) -> bool:
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None


def create_reminder(
    db: Session,
    user_id: str,
    title: str,
    remind_at: datetime,
    channel: str = "both",
    task_id: Optional[str] = None,
) -> Reminder:
    """Persist a new ``Reminder`` and return it.

    Raises:
        NotFoundError: when ``user_id`` is unknown, or when ``task_id`` is
            supplied but no matching task exists.
        ValidationError: when ``title`` is blank, ``remind_at`` is naive or
            in the past, or ``channel`` is outside ``ALLOWED_CHANNELS``.
        PermissionDeniedError: when ``task_id`` refers to a task owned by a
            different user.
    """
    # 1. user must exist
    user = db.query(User).filter(User.id == user_id).one_or_none()
    if user is None:
        raise NotFoundError(f"User {user_id!r} not found")

    # 2. title must be non-blank
    if not isinstance(title, str) or not title.strip():
        raise ValidationError("Title must be a non-blank string")

    # 3. remind_at must be a timezone-aware datetime
    if not isinstance(remind_at, datetime) or not _is_aware(remind_at):
        raise ValidationError("remind_at must be a timezone-aware datetime")

    # 4. remind_at must not be earlier than now
    if remind_at < now_utc():
        raise ValidationError("remind_at must not be earlier than now")

    # 5. channel must be one of the allowed values
    if channel not in ALLOWED_CHANNELS:
        raise ValidationError(
            f"channel must be one of {ALLOWED_CHANNELS}, got {channel!r}"
        )

    # 6. if task_id supplied, task must exist and belong to user
    if task_id is not None:
        task = db.query(Task).filter(Task.id == task_id).one_or_none()
        if task is None:
            raise NotFoundError(f"Task {task_id!r} not found")
        if task.user_id != user_id:
            raise PermissionDeniedError(
                f"Task {task_id!r} does not belong to user {user_id!r}"
            )

    reminder_kwargs = {
        "user_id": user_id,
        "title": title,
        "remind_at": remind_at,
        "channel": channel,
        "status": ReminderStatus.SCHEDULED,
    }
    if task_id is not None:
        reminder_kwargs["task_id"] = task_id

    reminder = Reminder(**reminder_kwargs)
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


def list_due_reminders(
    db: Session,
    now: Optional[datetime] = None,
) -> list[Reminder]:
    """Return reminders that are scheduled and due at or before ``now``.

    When ``now`` is ``None``, it defaults to UTC Now.
    """
    if now is None:
        now = now_utc()

    return (
        db.query(Reminder)
        .filter(Reminder.status == ReminderStatus.SCHEDULED)
        .filter(Reminder.remind_at <= now)
        .all()
    )


def mark_reminder_sent(db: Session, reminder_id: str) -> Reminder:
    """Mark a reminder as sent.

    Raises ``NotFoundError`` if no reminder with ``reminder_id`` exists.
    """
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id).one_or_none()
    if reminder is None:
        raise NotFoundError(f"Reminder {reminder_id!r} not found")

    reminder.status = ReminderStatus.SENT
    db.commit()
    db.refresh(reminder)
    return reminder


def mark_reminder_failed(db: Session, reminder_id: str) -> Reminder:
    """Mark a reminder as failed.

    Raises ``NotFoundError`` if no reminder with ``reminder_id`` exists.
    """
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id).one_or_none()
    if reminder is None:
        raise NotFoundError(f"Reminder {reminder_id!r} not found")

    reminder.status = ReminderStatus.FAILED
    db.commit()
    db.refresh(reminder)
    return reminder
