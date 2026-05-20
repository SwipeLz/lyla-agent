"""Log service: business logic for voice command audit logs.

Persists ``VoiceCommandLog`` rows used by later phases (agent runner) to debug
parsing and tool calls. Validation rules:

1. ``input_text`` must be a non-blank string.
2. ``parsed_actions`` must be JSON-serializable; ``None`` is acceptable.
3. If ``user_id`` is non-``None`` it must match an existing ``User``.
4. If ``device_id`` is non-``None`` it must match an existing ``Device``.

On any validation failure, no row is persisted.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.user import User
from app.models.voice_command_log import VoiceCommandLog
from app.services.exceptions import NotFoundError, ValidationError


def create_voice_command_log(
    db: Session,
    user_id: Optional[str],
    device_id: Optional[str],
    input_text: str,
    parsed_actions: Optional[Any] = None,
    response_text: Optional[str] = None,
    status: str = "success",
    *,
    metadata_json: Optional[dict] = None,
    request_received_at: Optional[datetime] = None,
    response_sent_at: Optional[datetime] = None,
) -> VoiceCommandLog:
    """Persist a new ``VoiceCommandLog`` and return it.

    Raises ``ValidationError`` when ``input_text`` is blank or
    ``parsed_actions``/``metadata_json`` is not JSON-serializable. Raises
    ``NotFoundError`` when ``user_id`` or ``device_id`` is supplied but
    does not match an existing row. Persists no rows when validation
    fails.
    """
    if not isinstance(input_text, str) or not input_text.strip():
        raise ValidationError("input_text must be a non-blank string")

    try:
        json.dumps(parsed_actions)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"parsed_actions must be JSON-serializable: {exc}"
        ) from exc

    if metadata_json is not None:
        try:
            json.dumps(metadata_json)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"metadata_json must be JSON-serializable: {exc}"
            ) from exc

    if user_id is not None:
        user = db.query(User).filter(User.id == user_id).one_or_none()
        if user is None:
            raise NotFoundError(f"User {user_id!r} not found")

    if device_id is not None:
        device = db.query(Device).filter(Device.id == device_id).one_or_none()
        if device is None:
            raise NotFoundError(f"Device {device_id!r} not found")

    log = VoiceCommandLog(
        user_id=user_id,
        device_id=device_id,
        input_text=input_text,
        parsed_actions=parsed_actions,
        response_text=response_text,
        status=status,
        metadata_json=metadata_json,
        request_received_at=request_received_at,
        response_sent_at=response_sent_at,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def update_voice_command_log_metadata(
    db: Session,
    log_id: str,
    metadata_json: dict,
) -> Optional[VoiceCommandLog]:
    """Overwrite ``metadata_json`` on an existing log row.

    Returns the refreshed row, or ``None`` if the row no longer exists.
    Mutating ``metadata_json`` is the documented exception to the
    append-only contract on ``VoiceCommandLog`` (see plan Task 9): only
    server-internal observability data is updated, never audit content.
    """
    try:
        json.dumps(metadata_json)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"metadata_json must be JSON-serializable: {exc}"
        ) from exc

    log = db.query(VoiceCommandLog).filter(VoiceCommandLog.id == log_id).one_or_none()
    if log is None:
        return None
    log.metadata_json = metadata_json
    db.commit()
    db.refresh(log)
    return log
