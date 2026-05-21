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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api._auth_dependencies import require_device_token, require_session
from app.config import settings
from app.db import get_db
from app.models.constants import DeviceCommandStatus, DeviceStatus
from app.models.device_command import DeviceCommand
from app.models.user import User
from app.schemas.devices import (
    AckResponse,
    DeviceDetailOut,
    DevicePairRequest,
    DevicePairResponse,
    DeviceStatusUpdate,
    DeviceUpdateRequest,
    PendingCommandOut,
)
from app.services import device_service
from app.services.exceptions import NotFoundError, ValidationError
from app.utils.timezone import now_utc

router = APIRouter(tags=["Devices"])


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

    has_telemetry = any(
        v is not None
        for v in (
            payload.firmware_version,
            payload.wifi_rssi_dbm,
            payload.battery_pct,
            payload.free_heap_bytes,
        )
    )
    if has_telemetry:
        try:
            device = device_service.update_telemetry(
                db,
                device.id,
                firmware_version=payload.firmware_version,
                wifi_rssi_dbm=payload.wifi_rssi_dbm,
                battery_pct=payload.battery_pct,
                free_heap_bytes=payload.free_heap_bytes,
            )
        except NotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device tidak ditemukan",
            )

    return {
        "status": device.status,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
    }


@router.post(
    "/devices/pair",
    response_model=DevicePairResponse,
    status_code=status.HTTP_201_CREATED,
)
def pair_device(
    payload: DevicePairRequest,
    db: Session = Depends(get_db),
    _: object = Depends(require_session),
) -> DevicePairResponse:
    user = (
        db.query(User).filter(User.email == settings.mvp_user_email).one_or_none()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MVP user {settings.mvp_user_email!r} not found",
        )

    try:
        device = device_service.pair_device(db, user.id, payload.name)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    config_json = {
        "user_id": user.id,
        "device_id": device.id,
        "device_code": device.device_code,
        "device_token": device.api_token,
        "base_url": settings.base_url,
        "wifi": {"ssid": "", "password": ""},
        "firmware_version": "0.1.0",
    }

    return DevicePairResponse(
        device_id=device.id,
        device_code=device.device_code,
        api_token=device.api_token or "",
        config_json=config_json,
    )


def _to_detail(device) -> DeviceDetailOut:
    return DeviceDetailOut(
        id=device.id,
        device_code=device.device_code,
        name=device.name,
        status=device.status,
        api_token=device.api_token,
        last_seen_at=device.last_seen_at.isoformat() if device.last_seen_at else None,
        firmware_version=device.firmware_version,
        wifi_rssi_dbm=device.wifi_rssi_dbm,
        battery_pct=device.battery_pct,
        free_heap_bytes=device.free_heap_bytes,
        created_at=device.created_at.isoformat() if device.created_at else None,
    )


@router.get(
    "/devices/id/{device_id}",
    response_model=DeviceDetailOut,
    dependencies=[Depends(require_session)],
)
def get_device_detail(
    device_id: str,
    db: Session = Depends(get_db),
) -> DeviceDetailOut:
    try:
        device = device_service.get_device_by_id(db, device_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device tidak ditemukan",
        )
    return _to_detail(device)


@router.patch(
    "/devices/id/{device_id}",
    response_model=DeviceDetailOut,
    dependencies=[Depends(require_session)],
)
def update_device(
    device_id: str,
    payload: DeviceUpdateRequest,
    db: Session = Depends(get_db),
) -> DeviceDetailOut:
    try:
        device = device_service.update_device_name(db, device_id, payload.name)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device tidak ditemukan",
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    return _to_detail(device)


@router.delete(
    "/devices/id/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_session)],
)
def delete_device(
    device_id: str,
    db: Session = Depends(get_db),
) -> None:
    try:
        device_service.delete_device(db, device_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device tidak ditemukan",
        )
