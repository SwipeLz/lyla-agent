"""Shared agent invocation flow used by `/agent/text` and `/agent/audio`.

Encapsulates the existing logic from `app.api.agent.post_agent_text`:
existence checks for user/device, timezone fallback, Agent Runtime
invocation, success-path `VoiceCommandLog`, and failure-path 500 +
error log row. Behavior MUST mirror the original handler bit-for-bit so
existing 189 tests continue to pass.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.agent.result import AgentRunResult
from app.agent.runtime import run_text
from app.config import settings
from app.models.device import Device
from app.models.user import User
from app.services import log_service


async def process_agent_text_command(
    db: Session,
    *,
    user_id: str,
    text: str,
    device_id: str | None = None,
    timezone: str | None = None,
) -> AgentRunResult:
    user = db.query(User).filter(User.id == user_id).one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User tidak ditemukan",
        )

    if device_id is not None:
        device = (
            db.query(Device).filter(Device.id == device_id).one_or_none()
        )
        if device is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device tidak ditemukan",
            )

    tz = timezone if timezone else settings.timezone

    try:
        result = await run_text(
            db,
            user_id=user_id,
            device_id=device_id,
            text=text,
            timezone=tz,
        )
    except Exception as exc:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        try:
            log_service.create_voice_command_log(
                db,
                user_id=user_id,
                device_id=device_id,
                input_text=text,
                parsed_actions=[],
                response_text=str(exc),
                status="error",
            )
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent runtime error",
        )

    log_service.create_voice_command_log(
        db,
        user_id=user_id,
        device_id=device_id,
        input_text=text,
        parsed_actions=result.actions,
        response_text=result.reply,
        status=result.status,
    )

    return result


__all__ = ["process_agent_text_command"]
