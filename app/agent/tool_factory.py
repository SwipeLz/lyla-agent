"""Per-Request Tool Factory for the Agent Runtime.

Builds the list of ADK-friendly Python callables that form the Tool Surface
(:mod:`app.agent` Phase 4). Each callable wraps a Phase 3 tool wrapper in
:mod:`app.tools` with the *Injected Context* (``db``, ``user_id``,
``device_id``) bound through a closure, so the model only ever sees the
*Model-Visible Arguments* listed in Requirement 2.1.

Per the design contract:

- The closures' Python signatures contain only Model-Visible Arguments. The
  Injected Context is invisible to the schema ADK derives from
  :func:`inspect.signature` (Requirements 2.1, 2.2, AR2).
- ``db``/``user_id``/``device_id`` supplied by the model (e.g. the LLM
  hallucinating those keyword arguments) are silently absorbed by
  ``**_kwargs`` and ignored; the bound Injected Context is used instead
  (Requirement 2.5, AR3).
- Datetime arguments visible to the model are documented as ISO 8601
  strings. The closure parses them into timezone-aware ``datetime``
  objects before delegating to the wrapper. Parsing failures (invalid
  format, naive datetimes, wrong type) are returned as a failure
  Tool Result Dict; the closure never raises (design "tool_factory").
- ``send_device_command`` short-circuits to a failure Tool Result Dict
  when ``device_id is None`` *without* calling the device service
  (Requirement 2.6, AR4).
- Each closure has its ``__name__`` set to the schema name and a short
  Indonesian ``__doc__`` so ADK's auto-generated function schema is
  correct and the agent prompt stays consistent with the rest of the
  Bahasa Indonesia agent surface (Requirement 1.6).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from app.tools import (
    device_tools,
    expense_tools,
    reminder_tools,
    summary_tools,
    task_tools,
)


def _parse_iso_datetime(
    value: Any, *, field_name: str
) -> tuple[datetime | None, str | None]:
    """Parse a model-supplied ISO 8601 string into an aware ``datetime``.

    Returns ``(dt, None)`` on success — including when ``value`` is already
    a timezone-aware ``datetime`` or when ``value is None`` (in which case
    ``dt`` is ``None``). Returns ``(None, error_message)`` when ``value``
    is not parseable as an ISO 8601 string, when the parsed datetime is
    naive (no ``tzinfo``), or when ``value`` is the wrong type.

    The trailing ``Z`` UTC marker is rewritten to ``+00:00`` because
    :meth:`datetime.fromisoformat` does not accept ``Z`` before Python
    3.11. The closures call this helper instead of catching exceptions
    inline so each datetime field gets a consistent failure message.
    """
    if value is None:
        return None, None
    error = (
        f"Argumen waktu '{field_name}' tidak valid; "
        "gunakan format ISO 8601 dengan zona waktu."
    )
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None:
            return value, None
        return None, error
    if not isinstance(value, str):
        return None, error
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None, error
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        return None, error
    return parsed, None


def build_tools(db, user_id, device_id) -> list[Callable[..., dict]]:
    """Return the five Tool Surface callables bound to a single request.

    The returned list always has exactly five elements in this order:
    ``create_task``, ``create_expense``, ``set_reminder``,
    ``get_today_summary``, ``send_device_command``. Every callable
    returns a Tool Result Dict and never raises; service-layer
    exceptions are converted to failure dicts inside the underlying
    Phase 3 wrappers.
    """

    def create_task(
        title: str,
        course: str | None = None,
        deadline_at: str | None = None,
        reminder_at: str | None = None,
        priority: str | None = None,
        **_kwargs,
    ) -> dict:
        deadline_dt, err = _parse_iso_datetime(deadline_at, field_name="deadline_at")
        if err is not None:
            return {"success": False, "type": "task", "error": err}
        reminder_dt, err = _parse_iso_datetime(reminder_at, field_name="reminder_at")
        if err is not None:
            return {"success": False, "type": "task", "error": err}
        return task_tools.create_task_tool(
            db=db,
            user_id=user_id,
            title=title,
            course=course,
            deadline_at=deadline_dt,
            reminder_at=reminder_dt,
            priority=priority,
        )

    create_task.__name__ = "create_task"
    create_task.__doc__ = (
        "Catat tugas akademik baru untuk pengguna saat ini. "
        "Argumen: title (str, wajib); course (str|None); "
        "deadline_at (string ISO 8601 dengan zona waktu, opsional); "
        "reminder_at (string ISO 8601 dengan zona waktu, opsional); "
        "priority (str|None)."
    )

    def create_expense(
        amount: int,
        category: str | None = None,
        note: str | None = None,
        spent_at: str | None = None,
        **_kwargs,
    ) -> dict:
        spent_dt, err = _parse_iso_datetime(spent_at, field_name="spent_at")
        if err is not None:
            return {"success": False, "type": "expense", "error": err}
        return expense_tools.create_expense_tool(
            db=db,
            user_id=user_id,
            amount=amount,
            category=category,
            note=note,
            spent_at=spent_dt,
        )

    create_expense.__name__ = "create_expense"
    create_expense.__doc__ = (
        "Catat pengeluaran pribadi pengguna saat ini. "
        "Argumen: amount (int rupiah penuh, > 0, wajib; LLM HARUS "
        "mengonversi shorthand seperti '10k'/'10rb'/'10 ribu' menjadi "
        "10000 dan '10jt'/'10 juta' menjadi 10000000 SEBELUM memanggil "
        "tool — jangan kirim 10 ketika pengguna bilang '10k'); "
        "category (str|None); note (str|None); spent_at (string ISO "
        "8601 dengan zona waktu, opsional)."
    )

    def set_reminder(
        title: str,
        remind_at: str,
        channel: str = "both",
        task_id: str | None = None,
        **_kwargs,
    ) -> dict:
        remind_dt, err = _parse_iso_datetime(remind_at, field_name="remind_at")
        if err is not None:
            return {"success": False, "type": "reminder", "error": err}
        if remind_dt is None:
            return {
                "success": False,
                "type": "reminder",
                "error": (
                    "remind_at wajib diisi dengan string ISO 8601 berzona waktu."
                ),
            }
        return reminder_tools.set_reminder_tool(
            db=db,
            user_id=user_id,
            title=title,
            remind_at=remind_dt,
            channel=channel,
            task_id=task_id,
        )

    set_reminder.__name__ = "set_reminder"
    set_reminder.__doc__ = (
        "Jadwalkan reminder untuk pengguna saat ini. "
        "Argumen: title (str, wajib); remind_at (string ISO 8601 dengan "
        "zona waktu, wajib); channel ('whatsapp'|'device'|'both', "
        "default 'both'); task_id (id task terkait, opsional)."
    )

    def get_today_summary(**_kwargs) -> dict:
        return summary_tools.get_today_summary_tool(db=db, user_id=user_id)

    get_today_summary.__name__ = "get_today_summary"
    get_today_summary.__doc__ = (
        "Ambil ringkasan hari ini (jumlah tugas yang jatuh tempo dan total "
        "pengeluaran) untuk pengguna saat ini. Tidak menerima argumen."
    )

    def send_device_command(
        face: str | None = None,
        sound: str | None = None,
        text: str | None = None,
        **_kwargs,
    ) -> dict:
        if device_id is None:
            return {
                "success": False,
                "type": "device_command",
                "error": "Tidak ada device yang terhubung untuk pengguna ini.",
            }
        return device_tools.send_device_command_tool(
            db=db,
            device_id=device_id,
            face=face,
            sound=sound,
            text=text,
        )

    send_device_command.__name__ = "send_device_command"
    send_device_command.__doc__ = (
        "Kirim perintah ke perangkat ESP32 milik pengguna. "
        "Argumen: face (str|None); sound (str|None); text (str|None). "
        "Minimal salah satu argumen harus diisi."
    )

    return [
        create_task,
        create_expense,
        set_reminder,
        get_today_summary,
        send_device_command,
    ]


__all__ = ["build_tools"]
