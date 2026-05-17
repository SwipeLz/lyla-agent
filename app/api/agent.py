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
``app/main.py`` includes it via ``app.include_router(agent.router)``
(task 6.3, separate task).
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
    """Run the Agent Runtime against ``payload.text`` and persist a log row.

    Order of operations is deliberate:

    1. Existence checks **before** invoking the runtime so we never
       waste an LLM call on a request that we know is invalid (Req
       5.3, 5.4 also require not invoking the runtime in those cases).
    2. ``run_text`` is wrapped in a broad ``try/except`` because Req
       6.6 demands a graceful 500 + error-status log row regardless of
       which layer raised. We re-raise as ``HTTPException(500, ...)``
       with a generic detail to avoid leaking internal messages to
       clients.
    3. The success-path log row is persisted *after* a successful
       runtime call so its ``parsed_actions``/``response_text`` exactly
       mirror what the client sees (Req 6.2, 6.4).
    """
    # Req 5.3: unknown user_id → 404 without invoking the runtime.
    user = db.query(User).filter(User.id == payload.user_id).one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User tidak ditemukan",
        )

    # Req 5.4: when device_id is supplied but no Device matches → 404.
    # When device_id is None the agent runs in "no paired device" mode
    # and ``send_device_command`` short-circuits inside the tool factory
    # (Req 2.6); no lookup is needed.
    if payload.device_id is not None:
        device = (
            db.query(Device).filter(Device.id == payload.device_id).one_or_none()
        )
        if device is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device tidak ditemukan",
            )

    # Req 5.5: prefer the request's timezone if provided non-empty;
    # otherwise fall back to the application default.
    tz = payload.timezone if payload.timezone else settings.timezone

    # Req 6.1: invoke the Agent Runtime exactly once.
    # Req 6.6: any unhandled exception → 500 + persist error log row.
    try:
        result = await run_text(
            db,
            user_id=payload.user_id,
            device_id=payload.device_id,
            text=payload.text,
            timezone=tz,
        )
    except Exception as exc:  # noqa: BLE001 — broad on purpose per Req 6.6
        # Persist an error log row so the failure is observable. We
        # deliberately use a fresh transactional context: if the runtime
        # left ``db`` in a dirty state, rollback first so the log insert
        # is not poisoned. ``log_service.create_voice_command_log``
        # itself does ``db.commit()``.
        try:
            db.rollback()
        except Exception:  # noqa: BLE001 — best-effort cleanup
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
            # Never let a logging failure mask the original 500 response.
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent runtime error",
        )

    # Req 6.2: persist exactly one VoiceCommandLog row mirroring the
    # response. Req 6.4: ``actions`` is forwarded as-is so the log and
    # the response agree.
    log_service.create_voice_command_log(
        db,
        user_id=payload.user_id,
        device_id=payload.device_id,
        input_text=payload.text,
        parsed_actions=result.actions,
        response_text=result.reply,
        status=result.status,
    )

    # Req 6.3: 200 OK with {reply, actions, device_feedback}. Req 6.5:
    # ``device_feedback`` was already chosen by the runtime via
    # ``_pick_device_feedback`` (last successful device_command Tool
    # Result Dict, or None).
    return AgentTextResponse(
        reply=result.reply,
        actions=result.actions,
        device_feedback=result.device_feedback,
    )
