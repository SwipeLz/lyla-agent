from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api._auth_dependencies import require_session
from app.api._rate_limit import get_client_ip, login_rate_limiter
from app.auth.passwords import verify_password
from app.auth.session import Session, session_store
from app.config import settings
from app.schemas.auth import LoginRequest, MeResponse


router = APIRouter(prefix="/auth", tags=["Auth"])


SESSION_COOKIE_NAME = "lyla_session"


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


@router.post("/login", response_model=MeResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> MeResponse:
    ip = get_client_ip(request)
    login_rate_limiter.check(ip)

    username_match = hmac.compare_digest(
        payload.username.encode("utf-8"),
        settings.dashboard_username.encode("utf-8"),
    )
    password_match = verify_password(payload.password, settings.dashboard_password_scrypt)

    if not (username_match and password_match):
        login_rate_limiter.record_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    login_rate_limiter.record_success(ip)
    session = session_store.create(payload.username)
    _set_session_cookie(response, session.token)
    return MeResponse(username=session.username, expires_at=session.expires_at)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> Response:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        session_store.revoke(token)
    _clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=MeResponse)
async def me(session: Session = Depends(require_session)) -> MeResponse:
    return MeResponse(username=session.username, expires_at=session.expires_at)
