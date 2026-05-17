"""Device tool wrappers.

Plain Python wrappers around :mod:`app.services.device_service`. Each function
returns a *Tool Result Dict* that is friendly to agent code — never an ORM
object and never a raised service exception.

Payload building rules for :func:`send_device_command_tool`:

- The ``payload`` dict is built from the keyword arguments ``face``, ``sound``,
  and ``text``. Only keys whose value is not ``None`` are included.
- If all three are ``None``, the function returns a failure dict immediately
  without calling the service.
- The ``command_type`` passed to the service is derived from which keys ended
  up in the payload:

  ===============================  ==============
  Non-``None`` keys                ``command_type``
  ===============================  ==============
  ``face`` only                    ``update_face``
  ``sound`` only                   ``play_sound``
  ``text`` only                    ``show_text``
  more than one of the three       ``composite``
  ===============================  ==============

Service exceptions (``ValidationError``, ``NotFoundError``,
``PermissionDeniedError``) are caught and converted to a failure dict with
``type = "device_command"``. Any other exception is allowed to propagate.
"""
from __future__ import annotations

from app.services import device_service
from app.services.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

_TYPE = "device_command"


def send_device_command_tool(
    db,
    device_id,
    face=None,
    sound=None,
    text=None,
) -> dict:
    """Build a device command payload and queue it via ``device_service``.

    See module docstring for payload-building and ``command_type`` rules.
    """
    payload = {
        k: v
        for k, v in {"face": face, "sound": sound, "text": text}.items()
        if v is not None
    }

    if not payload:
        return {
            "success": False,
            "type": _TYPE,
            "error": "Minimal satu dari face/sound/text harus diisi.",
        }

    if len(payload) == 1:
        only_key = next(iter(payload))
        command_type = {
            "face": "update_face",
            "sound": "play_sound",
            "text": "show_text",
        }[only_key]
    else:
        command_type = "composite"

    try:
        command = device_service.queue_device_command(
            db, device_id, command_type, payload
        )
    except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
        return {"success": False, "type": _TYPE, "error": str(exc)}

    return {
        "success": True,
        "type": _TYPE,
        "id": command.id,
        "message": "Perintah device dijadwalkan.",
    }
