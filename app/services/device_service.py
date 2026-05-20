"""Device service: business logic for IoT devices and queued commands.

All functions take a SQLAlchemy ``Session`` and primitive/Python objects.
They never depend on FastAPI, agent frameworks, or formatting concerns.

Responsibilities:
- Look up devices by their stable ``device_code``.
- Queue, list, mark-sent, and acknowledge device commands.
- Update a device's online/offline status and ``last_seen_at`` timestamp.
- Pair new devices and persist heartbeat telemetry (Phase 12).
"""
from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.models.constants import DeviceCommandStatus, DeviceStatus
from app.models.device import Device
from app.models.device_command import DeviceCommand
from app.models.user import User
from app.services.exceptions import NotFoundError, ValidationError
from app.utils.timezone import now_utc


def get_device_by_code(db: Session, device_code: str) -> Device:
    """Return the ``Device`` whose ``device_code`` matches.

    Raises ``NotFoundError`` if no such device exists.
    """
    device = (
        db.query(Device).filter(Device.device_code == device_code).one_or_none()
    )
    if device is None:
        raise NotFoundError(f"Device with code {device_code!r} not found")
    return device


def queue_device_command(
    db: Session,
    device_id: str,
    command_type: str,
    payload: dict,
) -> DeviceCommand:
    """Persist a new ``DeviceCommand`` in the ``PENDING`` state.

    - ``NotFoundError`` if no device with ``device_id`` exists.
    - ``ValidationError`` if ``command_type`` is not a non-blank string or
      ``payload`` is not a ``dict``.
    """
    device = db.query(Device).filter(Device.id == device_id).one_or_none()
    if device is None:
        raise NotFoundError(f"Device {device_id!r} not found")

    if not isinstance(command_type, str) or not command_type.strip():
        raise ValidationError("command_type must be a non-blank string")

    if not isinstance(payload, dict):
        raise ValidationError("payload must be a dict")

    command = DeviceCommand(
        device_id=device_id,
        command_type=command_type,
        payload=payload,
        status=DeviceCommandStatus.PENDING,
    )
    db.add(command)
    db.commit()
    db.refresh(command)
    return command


def list_pending_device_commands(
    db: Session,
    device_code: str,
) -> list[DeviceCommand]:
    """Return all ``PENDING`` commands for the device with ``device_code``.

    Raises ``NotFoundError`` if the device does not exist.
    """
    device = get_device_by_code(db, device_code)
    return (
        db.query(DeviceCommand)
        .filter(
            DeviceCommand.device_id == device.id,
            DeviceCommand.status == DeviceCommandStatus.PENDING,
        )
        .all()
    )


def mark_device_command_sent(db: Session, command_id: str) -> DeviceCommand:
    """Transition a command to ``SENT`` and stamp ``sent_at``.

    Raises ``NotFoundError`` if the command does not exist.
    """
    command = (
        db.query(DeviceCommand).filter(DeviceCommand.id == command_id).one_or_none()
    )
    if command is None:
        raise NotFoundError(f"DeviceCommand {command_id!r} not found")

    command.status = DeviceCommandStatus.SENT
    command.sent_at = now_utc()
    db.commit()
    db.refresh(command)
    return command


def ack_device_command(db: Session, command_id: str) -> DeviceCommand:
    """Transition a command to ``ACKNOWLEDGED`` and stamp ``acknowledged_at``.

    Raises ``NotFoundError`` if the command does not exist.
    """
    command = (
        db.query(DeviceCommand).filter(DeviceCommand.id == command_id).one_or_none()
    )
    if command is None:
        raise NotFoundError(f"DeviceCommand {command_id!r} not found")

    command.status = DeviceCommandStatus.ACKNOWLEDGED
    command.acknowledged_at = now_utc()
    db.commit()
    db.refresh(command)
    return command


def update_device_status(
    db: Session,
    device_code: str,
    status: str,
) -> Device:
    """Update a device's status and refresh its ``last_seen_at``.

    - ``NotFoundError`` if no device with ``device_code`` exists.
    - ``ValidationError`` if ``status`` is not one of ``ONLINE``/``OFFLINE``.
    """
    device = get_device_by_code(db, device_code)

    if status not in (DeviceStatus.ONLINE, DeviceStatus.OFFLINE):
        raise ValidationError(
            "status must be one of DeviceStatus.ONLINE or DeviceStatus.OFFLINE"
        )

    device.status = status
    device.last_seen_at = now_utc()
    db.commit()
    db.refresh(device)
    return device


def pair_device(db: Session, user_id: str, name: str) -> Device:
    """Create a new ``Device`` for ``user_id`` with a freshly minted token.

    - ``NotFoundError`` if no user with ``user_id`` exists.
    - ``ValidationError`` if ``name`` is not a non-blank string.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("name must be a non-blank string")

    user = db.query(User).filter(User.id == user_id).one_or_none()
    if user is None:
        raise NotFoundError(f"User {user_id!r} not found")

    device_code = "TASKBOT-" + secrets.token_hex(4).upper()
    api_token = "tk_live_" + secrets.token_urlsafe(32)

    device = Device(
        user_id=user_id,
        device_code=device_code,
        name=name,
        status=DeviceStatus.OFFLINE,
        api_token=api_token,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def update_telemetry(
    db: Session,
    device_id: str,
    *,
    firmware_version: str | None = None,
    wifi_rssi_dbm: int | None = None,
    battery_pct: int | None = None,
    free_heap_bytes: int | None = None,
) -> Device:
    """Persist heartbeat telemetry on the device row.

    Only non-``None`` fields are written; absent fields preserve previous
    values. Raises ``NotFoundError`` if no device with ``device_id``
    exists.
    """
    device = db.query(Device).filter(Device.id == device_id).one_or_none()
    if device is None:
        raise NotFoundError(f"Device {device_id!r} not found")

    if firmware_version is not None:
        device.firmware_version = firmware_version
    if wifi_rssi_dbm is not None:
        device.wifi_rssi_dbm = wifi_rssi_dbm
    if battery_pct is not None:
        device.battery_pct = battery_pct
    if free_heap_bytes is not None:
        device.free_heap_bytes = free_heap_bytes

    db.commit()
    db.refresh(device)
    return device
