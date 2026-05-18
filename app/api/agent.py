"""Phase 5 — ``POST /agent/text`` endpoint.

This handler is the single HTTP entry point that exposes the Agent
Runtime to clients (frontend, ESP32 voice path, dashboard debug calls).
It mediates four concerns:

1. **Request validation** (Req 5.1, 5.2): Pydantic enforces non-blank
   ``text``; FastAPI returns 422 automatically before this handler runs
   if the body shape is wrong.
2. **Existence checks** (Req 5.3, 5.4): the user (always) and the device
   (only when ``device_id`` is supplied) must exist; otherwise 404 is
   returned and the Agent Runtime is *not* invoked.
3. **Timezone resolution** (Req 5.5): use the request's ``timezone``
   when supplied non-empty; otherwise fall back to ``settings.timezone``
   (default ``"Asia/Jakarta"``).
4. **Logging + reply assembly** (Req 6.1–6.6): invoke ``run_text``
   exactly once; on success, persist a ``VoiceCommandLog`` row mirroring
   the response and return ``{reply, actions, device_feedback}``; on
   any unhandled runtime exception, persist an error log row and raise
   a generic 500 (the FastAPI default JSON body contains only
   ``{"detail": ...}``, never a stack trace, satisfying Req 6.6).

Router mounting
---------------
The router has no ``prefix``; the route path itself is ``/agent/text``.
``app/main.py`` includes it via ``app.include_router(agent.router)``.

Phase 10 note: the shared invocation flow lives in
:func:`app.api._agent_helpers.process_agent_text_command` so
:func:`app.api.audio.post_agent_audio` can reuse it. This handler keeps
its original inline form because existing tests monkeypatch
``app.api.agent.run_text`` directly; routing through the helper would
break that patch surface (revert documented in the Phase 10 plan).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agent.runtime import run_text
from app.config import settings
from app.db import get_db
from app.models.device import Device
from app.models.user import User
from app.schemas.agent import AgentTextRequest, AgentTextResponse
from app.services import log_service

router = APIRouter(tags=["Agent"])


@router.post("/agent/text", response_model=AgentTextResponse)
async def post_agent_text(
    payload: AgentTextRequest,
    db: Session = Depends(get_db),
) -> AgentTextResponse:
    """Run the Agent Runtime against ``payload.text`` and persist a log row."""
    user = db.query(User).filter(User.id == payload.user_id).one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User tidak ditemukan",
        )

    if payload.device_id is not None:
        device = (
            db.query(Device).filter(Device.id == payload.device_id).one_or_none()
        )
        if device is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device tidak ditemukan",
            )

    tz = payload.timezone if payload.timezone else settings.timezone

    try:
        result = await run_text(
            db,
            user_id=payload.user_id,
            device_id=payload.device_id,
            text=payload.text,
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
                user_id=payload.user_id,
                device_id=payload.device_id,
                input_text=payload.text,
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
        user_id=payload.user_id,
        device_id=payload.device_id,
        input_text=payload.text,
        parsed_actions=result.actions,
        response_text=result.reply,
        status=result.status,
    )

    return AgentTextResponse(
        reply=result.reply,
        actions=result.actions,
        device_feedback=result.device_feedback,
    )
