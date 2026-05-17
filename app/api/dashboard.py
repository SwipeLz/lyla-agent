"""Phase 8 — Minimal Dashboard API.

HTTP routes consumed by the internal/dev dashboard UI and debug CLIs.
Every route delegates to the existing Service Layer (Phase 3) and the
``get_today_summary_tool`` wrapper; no ORM writes happen in this module
beyond what the services and tool wrappers already perform.

Routing
-------
The router is mounted with **full paths** (no ``prefix``) so that
``app.include_router(dashboard.router)`` in ``app/main.py`` exposes the
routes under ``/dashboard/...`` directly — matching the convention used
by :mod:`app.api.devices` and the path layout in the spec
(``GET /dashboard/tasks`` etc., per Requirements 12.1, 12.3, 12.5,
13.1–13.5).

Auth
----
``require_dashboard_auth`` honours ``settings.dashboard_auth_mode``:

- ``"none"`` (MVP default per design.md "Open Decision"): the dependency
  passes through and no header is required (Req 14.2).
- ``"shared_header"``: the request must carry an ``X-Dashboard-Token``
  header whose value equals ``settings.dashboard_token``; otherwise the
  endpoint returns HTTP 401 without touching the database (Req 14.3).
  The header value is never logged or echoed back to the caller.
- Any other value is treated as a misconfiguration and surfaces HTTP
  500 to make the operator notice rather than silently fall open.

Local error mapping
-------------------
Per the orchestrator's note, this task maps Service Layer exceptions
(:class:`NotFoundError`, :class:`ValidationError`,
:class:`PermissionDeniedError`) to HTTP 404/422/403 **locally** via
``try/except`` blocks. Task 10.4 will install global exception handlers
as a backstop, but the local handling here keeps the contract correct
even before those handlers are wired in.

User-existence gate
-------------------
Every endpoint that takes a ``user_id`` first verifies that the user
exists (Req 12.7 / 13.6). Nonexistent users yield HTTP 404 *before* any
write or service call so we never partially mutate state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.device import Device
from app.models.user import User
from app.models.voice_command_log import VoiceCommandLog
from app.schemas.dashboard import (
    DeviceOut,
    ExpenseIn,
    ExpenseOut,
    LogOut,
    SummaryOut,
    TaskOut,
    TaskPatch,
)
from app.services import expense_service, task_service
from app.services.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.tools.summary_tools import get_today_summary_tool

router = APIRouter(tags=["Dashboard"])


# --------------------------------------------------------------------------- #
# Auth dependency                                                              #
# --------------------------------------------------------------------------- #


def require_dashboard_auth(
    x_dashboard_token: str | None = Header(default=None, alias="X-Dashboard-Token"),
) -> None:
    """Dashboard auth gate driven by ``settings.dashboard_auth_mode``.

    - ``"none"``: pass through without checking any header (Req 14.2).
    - ``"shared_header"``: require ``X-Dashboard-Token`` to equal
      ``settings.dashboard_token``; otherwise raise HTTP 401 (Req 14.3).
    - Any other value: HTTP 500, signalling misconfiguration.
    """
    mode = settings.dashboard_auth_mode
    if mode == "none":
        return
    if mode == "shared_header":
        expected = settings.dashboard_token
        if not expected or x_dashboard_token != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized",
            )
        return
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Invalid dashboard_auth_mode configuration",
    )


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _ensure_user_exists(db: Session, user_id: str) -> None:
    """Raise HTTP 404 if no user with ``user_id`` exists.

    Centralised so every endpoint guarded by ``user_id`` shares the same
    exact response shape (Req 12.7, 13.6). Runs before any mutation.
    """
    if db.query(User).filter(User.id == user_id).first() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User tidak ditemukan",
        )


def _map_service_exceptions(exc: Exception) -> HTTPException:
    """Map Service Layer exceptions to HTTPExceptions.

    Used inside ``try/except`` blocks so the dashboard router has a
    well-defined HTTP contract even before task 10.4 installs the global
    exception handlers (Req 12.7, 13.7).
    """
    if isinstance(exc, NotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc) or "Not found"
        )
    if isinstance(exc, ValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc) or "Validation error",
        )
    if isinstance(exc, PermissionDeniedError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc) or "Permission denied",
        )
    # Anything else propagates: it's a bug or infrastructure problem, not
    # a user-facing condition.
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error"
    )


# --------------------------------------------------------------------------- #
# Tasks                                                                        #
# --------------------------------------------------------------------------- #


@router.get(
    "/dashboard/tasks",
    response_model=list[TaskOut],
    dependencies=[Depends(require_dashboard_auth)],
)
def list_tasks(
    user_id: str = Query(...),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[TaskOut]:
    """Return tasks owned by ``user_id``, optionally filtered by ``status``.

    Validates: Requirements 12.1, 12.2, 13.6.
    """
    _ensure_user_exists(db, user_id)
    rows = task_service.list_tasks(db, user_id, status=status)
    return [TaskOut.model_validate(row) for row in rows]


@router.patch(
    "/dashboard/tasks/{task_id}",
    response_model=TaskOut,
    dependencies=[Depends(require_dashboard_auth)],
)
def patch_task(
    task_id: str,
    patch: TaskPatch,
    db: Session = Depends(get_db),
) -> TaskOut:
    """Apply a partial update to a task.

    Only fields supplied in the JSON body (non-``None``) are applied.
    Validation rules mirror :func:`task_service.create_task` and surface
    as HTTP 422; missing tasks surface as HTTP 404.

    Validates: Requirements 12.3, 12.4, 12.7, 13.7.
    """
    # ``model_dump(exclude_unset=True)`` so omitted fields are not sent
    # as ``None`` — the service-layer ``update_task`` already drops
    # ``None`` values, but excluding them here keeps the contract clear.
    fields = patch.model_dump(exclude_unset=True)
    try:
        task = task_service.update_task(db, task_id, **fields)
    except (NotFoundError, ValidationError, PermissionDeniedError) as exc:
        raise _map_service_exceptions(exc)
    return TaskOut.model_validate(task)


@router.delete(
    "/dashboard/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_dashboard_auth)],
)
def delete_task(
    task_id: str,
    db: Session = Depends(get_db),
) -> Response:
    """Delete a task by id and return HTTP 204 on success.

    Validates: Requirements 12.5, 12.6, 12.7.
    """
    try:
        task_service.delete_task(db, task_id)
    except (NotFoundError, ValidationError, PermissionDeniedError) as exc:
        raise _map_service_exceptions(exc)
    # Explicit 204 with empty body so FastAPI does not try to serialize
    # ``None`` into a JSON ``null``.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Expenses                                                                     #
# --------------------------------------------------------------------------- #


@router.get(
    "/dashboard/expenses",
    response_model=list[ExpenseOut],
    dependencies=[Depends(require_dashboard_auth)],
)
def list_expenses(
    user_id: str = Query(...),
    start_at: Optional[datetime] = Query(default=None),
    end_at: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ExpenseOut]:
    """Return expenses for ``user_id`` within an optional ``[start_at,
    end_at]`` window.

    ``start_at`` / ``end_at`` are parsed as ISO 8601 datetimes by
    Pydantic; values that are not valid ISO 8601 strings are rejected by
    FastAPI with HTTP 422 before this handler runs.

    Validates: Requirements 13.1, 13.6, 13.7.
    """
    _ensure_user_exists(db, user_id)
    try:
        rows = expense_service.list_expenses(
            db, user_id, start_at=start_at, end_at=end_at
        )
    except (NotFoundError, ValidationError, PermissionDeniedError) as exc:
        raise _map_service_exceptions(exc)
    return [ExpenseOut.model_validate(row) for row in rows]


@router.post(
    "/dashboard/expenses",
    response_model=ExpenseOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_dashboard_auth)],
)
def create_expense(
    payload: ExpenseIn,
    db: Session = Depends(get_db),
) -> ExpenseOut:
    """Create a new expense and return HTTP 201 with the persisted row.

    Service-layer validation (positive integer ``amount``, timezone-aware
    ``spent_at``) is applied downstream and surfaces as HTTP 422.

    Validates: Requirements 13.2, 13.6, 13.7.
    """
    _ensure_user_exists(db, payload.user_id)
    try:
        expense = expense_service.create_expense(
            db,
            user_id=payload.user_id,
            amount=payload.amount,
            category=payload.category,
            note=payload.note,
            spent_at=payload.spent_at,
        )
    except (NotFoundError, ValidationError, PermissionDeniedError) as exc:
        raise _map_service_exceptions(exc)
    return ExpenseOut.model_validate(expense)


# --------------------------------------------------------------------------- #
# Summary, logs, devices                                                       #
# --------------------------------------------------------------------------- #


@router.get(
    "/dashboard/summary",
    response_model=SummaryOut,
    dependencies=[Depends(require_dashboard_auth)],
)
def get_summary(
    user_id: str = Query(...),
    db: Session = Depends(get_db),
) -> SummaryOut:
    """Return today's summary using the same Asia/Jakarta calendar-day
    window as :func:`get_today_summary_tool`.

    The user-existence gate runs first so a missing user yields HTTP 404
    before invoking the tool wrapper (which would otherwise produce a
    Tool Result Dict with ``success=False``).

    Validates: Requirements 13.3, 13.6.
    """
    _ensure_user_exists(db, user_id)
    result = get_today_summary_tool(db, user_id)
    # The tool wrapper returns ``success=False`` only when the user is
    # missing; we already ruled that out, so any failure here would be a
    # genuine bug. We still defensively map it to 500 instead of
    # returning a half-built ``SummaryOut`` with default zeros.
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error") or "Summary unavailable",
        )
    return SummaryOut(
        tasks_due_today=int(result["tasks_due_today"]),
        total_expenses_today=int(result["total_expenses_today"]),
    )


@router.get(
    "/dashboard/logs",
    response_model=list[LogOut],
    dependencies=[Depends(require_dashboard_auth)],
)
def list_logs(
    user_id: str = Query(...),
    db: Session = Depends(get_db),
) -> list[LogOut]:
    """Return ``VoiceCommandLog`` rows for ``user_id`` ordered most-recent
    first by ``created_at`` (Req 13.4)."""
    _ensure_user_exists(db, user_id)
    rows = (
        db.query(VoiceCommandLog)
        .filter(VoiceCommandLog.user_id == user_id)
        .order_by(VoiceCommandLog.created_at.desc())
        .all()
    )
    return [LogOut.model_validate(row) for row in rows]


@router.get(
    "/dashboard/devices",
    response_model=list[DeviceOut],
    dependencies=[Depends(require_dashboard_auth)],
)
def list_devices(
    user_id: str = Query(...),
    db: Session = Depends(get_db),
) -> list[DeviceOut]:
    """Return ``Device`` rows belonging to ``user_id`` (Req 13.5)."""
    _ensure_user_exists(db, user_id)
    rows = db.query(Device).filter(Device.user_id == user_id).all()
    return [DeviceOut.model_validate(row) for row in rows]
