"""Phase 7 — Device Command Queue API.

Three device-facing routes used by the ESP32 device, each guarded by the
``X-Device-Token`` header dependency:

- ``GET    /devices/{device_code}/commands/pending``
- ``POST   /devices/{device_code}/commands/{command_id}/ack``
- ``POST   /devices/{device_code}/status``

The router is intentionally mounted with **full paths** (no ``prefix``) so that
``app.include_router(devices.router)`` in ``app/main.py`` exposes the routes
under ``/devices/...`` without an extra layer of indirection.

Implementation notes:

- ``require_device_token`` runs **before** any database lookup. A missing or
  mismatched ``X-Device-Token`` header — including the case where
  ``settings.device_api_token`` itself is empty — short-circuits to HTTP 401
  without touching the DB (Req 9.2). The token value is never echoed in the
  response or logged anywhere.
- ``GET /devices/{device_code}/commands/pending`` performs the **Atomic
  Mark-Sent** operation in a single transaction: read all ``PENDING`` rows
  (``with_for_update()`` for forward-compatibility with Postgres), serialize
  them into the response, then transition each row to ``SENT`` with
  ``sent_at = now_utc()`` before committing once. Two consecutive polls with
  no new pending command in between therefore yield ``[]`` on the second call
  (Req 10.3).
- The ack endpoint enforces the device/command relationship at the API layer
  (Req 11.2): if the supplied ``command_id`` does not exist or does not belong
  to the supplied ``device_code``, it returns 404 without mutating any row.
- The status endpoint validates ``status ∈ {"online", "offline"}`` at the API
  layer (Req 11.4). The Service Layer would also reject invalid values via
  ``ValidationError``, but doing the check here keeps the 422 contract local
  to HTTP and avoids leaking a service exception type as a 500.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.constants import DeviceCommandStatus, DeviceStatus
from app.models.device_command import DeviceCommand
from app.schemas.devices import AckResponse, DeviceStatusUpdate, PendingCommandOut
from app.services import device_service
from app.services.exceptions import NotFoundError
from app.utils.timezone import now_utc

router = APIRouter(tags=["Devices"])


def require_device_token(
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
) -> None:
    """Dependency that enforces the ``X-Device-Token`` header.

    Returns ``None`` on success; raises ``HTTPException(401)`` otherwise.

    The check fails closed when ``settings.device_api_token`` is empty so that
    a misconfigured deployment cannot accidentally accept arbitrary clients.
    The header value is never logged or echoed back to the caller.
    """
    expected = settings.device_api_token
    if not expected or x_device_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )


@router.get(
    "/devices/{device_code}/commands/pending",
    response_model=list[PendingCommandOut],
    dependencies=[Depends(require_device_token)],
)
def list_pending_commands(
    device_code: str,
    db: Session = Depends(get_db),
) -> list[PendingCommandOut]:
    """Return and atomically mark-sent all pending commands for a device."""
    try:
        device = device_service.get_device_by_code(db, device_code)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device tidak ditemukan",
        )

    pending = (
        db.query(DeviceCommand)
        .filter(
            DeviceCommand.device_id == device.id,
            DeviceCommand.status == DeviceCommandStatus.PENDING,
        )
        .with_for_update()
        .all()
    )

    if not pending:
        return []

    out: list[PendingCommandOut] = []
    timestamp = now_utc()
    for cmd in pending:
        out.append(
            PendingCommandOut(
                command_id=cmd.id,
                command_type=cmd.command_type,
                payload=cmd.payload if isinstance(cmd.payload, dict) else {},
                created_at=cmd.created_at.isoformat() if cmd.created_at else "",
            )
        )
        cmd.status = DeviceCommandStatus.SENT
        cmd.sent_at = timestamp

    db.commit()
    return out


@router.post(
    "/devices/{device_code}/commands/{command_id}/ack",
    response_model=AckResponse,
    dependencies=[Depends(require_device_token)],
)
def ack_command(
    device_code: str,
    command_id: str,
    db: Session = Depends(get_db),
) -> AckResponse:
    """Acknowledge a previously-sent command for a device."""
    try:
        device = device_service.get_device_by_code(db, device_code)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device tidak ditemukan",
        )

    command = (
        db.query(DeviceCommand)
        .filter(
            DeviceCommand.id == command_id,
            DeviceCommand.device_id == device.id,
        )
        .one_or_none()
    )
    if command is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Command tidak ditemukan",
        )

    device_service.ack_device_command(db, command_id)
    return AckResponse(success=True, command_id=command_id)


@router.post(
    "/devices/{device_code}/status",
    dependencies=[Depends(require_device_token)],
)
def update_status(
    device_code: str,
    payload: DeviceStatusUpdate,
    db: Session = Depends(get_db),
) -> dict:
    """Update a device's online/offline status."""
    if payload.status not in (DeviceStatus.ONLINE, DeviceStatus.OFFLINE):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status harus 'online' atau 'offline'",
        )

    try:
        device = device_service.update_device_status(db, device_code, payload.status)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device tidak ditemukan",
        )

    return {
        "status": device.status,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
    }
