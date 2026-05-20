"""Shared agent invocation flow used by `/agent/text` and `/agent/audio`.

Encapsulates the existing logic from `app.api.agent.post_agent_text`:
existence checks for user/device, timezone fallback, Agent Runtime
invocation, success-path `VoiceCommandLog`, and failure-path 500 +
error log row. Behavior MUST mirror the original handler bit-for-bit so
existing 189 tests continue to pass.

Phase 11b: returns ``AgentInvocation`` (a small dataclass wrapping the
existing ``AgentRunResult`` plus the persisted ``log_id``) so the
audio handler can populate the TTS cache keyed by the same id that
ESP firmware will later use to fetch synthesized audio bytes.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.agent.result import AgentRunResult
from app.agent.runtime import run_text
from app.config import settings
from app.models.device import Device
from app.models.user import User
from app.services import log_service


@dataclass
class AgentInvocation:
    result: AgentRunResult
    log_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _empty_metadata() -> dict[str, Any]:
    return {
        "stage_timings_ms": {
            "validate": None,
            "stt": None,
            "agent": None,
            "classify": None,
            "tts": None,
        },
        "transcription": None,
        "directive": None,
        "audio": None,
        "tts": None,
        "client": {},
        "error": None,
    }


async def process_agent_text_command(
    db: Session,
    *,
    user_id: str,
    text: str,
    device_id: str | None = None,
    timezone: str | None = None,
) -> AgentInvocation:
    request_received_at = dt.datetime.now(tz=dt.timezone.utc)
    metadata = _empty_metadata()

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

    agent_start = time.perf_counter()
    try:
        result = await run_text(
            db,
            user_id=user_id,
            device_id=device_id,
            text=text,
            timezone=tz,
        )
    except Exception as exc:  # noqa: BLE001
        agent_ms = int((time.perf_counter() - agent_start) * 1000)
        response_sent_at = dt.datetime.now(tz=dt.timezone.utc)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        metadata["stage_timings_ms"]["agent"] = agent_ms
        metadata["error"] = {"layer": "agent", "detail": str(exc)}
        try:
            log_service.create_voice_command_log(
                db,
                user_id=user_id,
                device_id=device_id,
                input_text=text,
                parsed_actions=[],
                response_text=str(exc),
                status="error",
                metadata_json=metadata,
                request_received_at=request_received_at,
                response_sent_at=response_sent_at,
            )
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent runtime error",
        )

    agent_ms = int((time.perf_counter() - agent_start) * 1000)
    response_sent_at = dt.datetime.now(tz=dt.timezone.utc)
    metadata["stage_timings_ms"]["agent"] = agent_ms

    log_row = log_service.create_voice_command_log(
        db,
        user_id=user_id,
        device_id=device_id,
        input_text=text,
        parsed_actions=result.actions,
        response_text=result.reply,
        status=result.status,
        metadata_json=metadata,
        request_received_at=request_received_at,
        response_sent_at=response_sent_at,
    )

    return AgentInvocation(result=result, log_id=log_row.id, metadata=metadata)


__all__ = ["AgentInvocation", "process_agent_text_command"]
