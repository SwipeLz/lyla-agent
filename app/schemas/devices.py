"""Pydantic v2 schemas for Phase 7 Device Command Queue API.

These schemas back the three device-facing HTTP routes:
- ``GET /devices/{device_code}/commands/pending`` (response items: ``PendingCommandOut``)
- ``POST /devices/{device_code}/commands/{command_id}/ack`` (response: ``AckResponse``)
- ``POST /devices/{device_code}/status`` (request body: ``DeviceStatusUpdate``)

Note on ``command_id`` typing:
    Requirements 10.1 / 11.1 mention ``command_id: int``, but the actual
    ``DeviceCommand.id`` column is a ``String`` UUID (see
    ``app/models/device_command.py``) and the Service Layer signatures already
    use ``command_id: str`` (see ``device_service.ack_device_command``). The
    design document also uses ``str``. To stay consistent with the existing
    schema and Service Layer (which Phase 4-8 must not modify), we serialize
    ``command_id`` as ``str`` here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PendingCommandOut(BaseModel):
    """One pending command returned to the device on poll.

    Backs the JSON list returned by
    ``GET /devices/{device_code}/commands/pending``.
    """

    command_id: str = Field(
        ...,
        description="Identifier of the DeviceCommand row (UUID string).",
    )
    command_type: str = Field(
        ...,
        description="Logical command type (e.g. 'show_text', 'play_sound').",
    )
    payload: dict = Field(
        ...,
        description="Free-form JSON payload as stored on the DeviceCommand row.",
    )
    created_at: str = Field(
        ...,
        description="ISO 8601 timestamp of when the command was queued.",
    )


class AckResponse(BaseModel):
    """Response body for the command ack endpoint.

    Backs ``POST /devices/{device_code}/commands/{command_id}/ack``.
    """

    success: bool = Field(
        ...,
        description="Always True on a 200 response; included for client clarity.",
    )
    command_id: str = Field(
        ...,
        description="Echoes the acknowledged command's identifier.",
    )


class DeviceStatusUpdate(BaseModel):
    """Request body for the device status update endpoint.

    Backs ``POST /devices/{device_code}/status``. The handler is responsible for
    rejecting values outside ``{"online", "offline"}`` with HTTP 422 (per
    Requirement 11.4); this schema only enforces the field's presence and type.

    Phase 12 extends this with optional telemetry fields. ESP firmware may send
    none of them (backward-compatible), or any subset. The handler routes
    non-``None`` telemetry to ``device_service.update_telemetry``.
    """

    status: str = Field(
        ...,
        description="Reported device status; expected to be 'online' or 'offline'.",
    )
    firmware_version: str | None = None
    wifi_rssi_dbm: int | None = None
    battery_pct: int | None = None
    free_heap_bytes: int | None = None


class DevicePairRequest(BaseModel):
    name: str = Field(..., description="Operator-friendly device label.")


class DevicePairResponse(BaseModel):
    """Response body for ``POST /devices/pair`` (Phase 12).

    ``config_json`` is the ready-to-paste blob the operator saves to the SD
    card as ``/sd/config.json``. ``api_token`` is included at the top level
    only on this pair response so the operator can copy it; never expose it
    via GET endpoints.
    """

    device_id: str
    device_code: str
    api_token: str
    config_json: dict
