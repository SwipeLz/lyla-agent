from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DbSession

from app.auth.session import Session, session_store
from app.config import settings
from app.db import get_db
from app.models.device import Device


SESSION_COOKIE_NAME = "lyla_session"


async def require_session(request: Request) -> Session:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    session = session_store.get(token or "")
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session


async def require_device_token(
    request: Request,
    db: DbSession = Depends(get_db),
) -> Device | None:
    if not settings.require_device_token:
        return None
    token = request.headers.get("X-Device-Token")
    if not token:
        raise HTTPException(status_code=401, detail="Device token required")
    device = db.query(Device).filter(Device.api_token == token).one_or_none()
    if device is None:
        raise HTTPException(status_code=401, detail="Invalid device token")
    return device
