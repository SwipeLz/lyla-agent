"""ADK-discoverable dev agent for the Taskbot project.

Why this file exists
--------------------

The production agent (``app.agent.runtime.run_text``) builds a fresh
``Agent`` *per HTTP request* via ``app.agent.tool_factory.build_tools`` so it
can inject the request-scoped ``db``, ``user_id``, and ``device_id`` into
the tools through closures. ADK CLI tools (``adk web``, ``adk run``,
``adk api_server``) cannot use that factory — they discover agents by
importing a module and reading a top-level ``root_agent`` symbol at
process-start time, before any HTTP request exists.

This file therefore exposes a *thin shell* ``root_agent`` purely so the
dev UI can drive the LLM end-to-end. The tools below are intentionally
**stubs**: they validate arguments and return well-shaped Tool Result
Dicts, but they do NOT touch the database. Use them to:

- Iterate on the Indonesian system prompt.
- Observe how Gemini decomposes user requests into tool calls.
- Sanity-check tool *signatures* (names, argument types, doc strings).

For real execution against the SQLite DB, hit
``POST /agent/text`` (or run ``python -m scripts.run_agent_text``).

Drift prevention
----------------

The system instruction (``INSTRUCTION``) and the model identifier are
**imported** from the production modules so they cannot drift:

- ``INSTRUCTION`` ← ``app.agent.adk_agent.INSTRUCTION``
- model           ← ``app.config.settings.google_adk_model``

Tool *names* are also kept identical to the production tools in
``app.agent.tool_factory``. If you add or rename a tool there, mirror the
change here (and the smoke test ``app/tests/test_dev_agent_parity.py``
will fail loudly if you forget).

Path bootstrap
--------------

When ADK CLI tools are run from the ``agents/`` directory, the project
root is **not** on :data:`sys.path`, so ``from app.* import …`` would
fail. We therefore prepend the project root (two levels up from this
file) to ``sys.path`` before doing the cross-package imports. This is a
no-op when imported from a context where the project root is already on
the path (e.g. from pytest at the repo root).
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# --- sys.path & .env bootstrap ----------------------------------------------
# This file lives at: <project_root>/agents/taskbot_agent/agent.py
# So <project_root> is parents[2].
_PROJECT_ROOT = _Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

# ADK reads GOOGLE_API_KEY (and friends) from os.environ at runtime, not from
# Pydantic settings. Load the project-root .env into the process environment
# so ``adk web`` works from any CWD without a duplicate per-agent .env.
try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(_PROJECT_ROOT / ".env", override=False)
except ImportError:  # pragma: no cover - dotenv ships with google-adk
    pass
# ----------------------------------------------------------------------------

from google.adk.agents import Agent  # noqa: E402

from app.agent.adk_agent import INSTRUCTION  # noqa: E402
from app.config import settings  # noqa: E402


# ---------------------------------------------------------------------------
# Stub tools — same signatures as ``app.agent.tool_factory.build_tools``,
# but no DB access. Each returns a Tool Result Dict shaped like the real
# tool would, so the LLM behaviour observed in ``adk web`` matches what
# the production runtime will produce.
# ---------------------------------------------------------------------------


def create_task(
    title: str,
    course: str | None = None,
    deadline_at: str | None = None,
    reminder_at: str | None = None,
    priority: str | None = None,
    **_kwargs,
) -> dict:
    """Catat tugas akademik baru (DEV STUB — tidak menyimpan ke database).

    Argumen: title (str, wajib); course (str|None);
    deadline_at (ISO 8601, opsional); reminder_at (ISO 8601, opsional);
    priority (str|None).
    """
    return {
        "success": True,
        "type": "task",
        "stub": True,
        "task": {
            "title": title,
            "course": course,
            "deadline_at": deadline_at,
            "reminder_at": reminder_at,
            "priority": priority,
        },
    }


def create_expense(
    amount: int,
    category: str | None = None,
    note: str | None = None,
    spent_at: str | None = None,
    **_kwargs,
) -> dict:
    """Catat pengeluaran pribadi (DEV STUB — tidak menyimpan ke database).

    Argumen: amount (int rupiah, > 0, wajib); category (str|None);
    note (str|None); spent_at (ISO 8601, opsional).
    """
    if not isinstance(amount, int) or amount <= 0:
        return {
            "success": False,
            "type": "expense",
            "error": "amount harus berupa int positif (rupiah).",
        }
    return {
        "success": True,
        "type": "expense",
        "stub": True,
        "expense": {
            "amount": amount,
            "category": category,
            "note": note,
            "spent_at": spent_at,
        },
    }


def set_reminder(
    title: str,
    remind_at: str,
    channel: str = "both",
    task_id: str | None = None,
    **_kwargs,
) -> dict:
    """Jadwalkan reminder (DEV STUB — tidak menyimpan ke database).

    Argumen: title (str, wajib); remind_at (ISO 8601, wajib);
    channel ('whatsapp'|'device'|'both'); task_id (opsional).
    """
    if channel not in {"whatsapp", "device", "both"}:
        return {
            "success": False,
            "type": "reminder",
            "error": "channel harus salah satu: whatsapp, device, both.",
        }
    return {
        "success": True,
        "type": "reminder",
        "stub": True,
        "reminder": {
            "title": title,
            "remind_at": remind_at,
            "channel": channel,
            "task_id": task_id,
        },
    }


def get_today_summary(**_kwargs) -> dict:
    """Ringkasan hari ini (DEV STUB — angka palsu untuk eksperimen prompt).

    Tidak menerima argumen.
    """
    return {
        "success": True,
        "type": "summary",
        "stub": True,
        "summary": {
            "tasks_due_today": 2,
            "total_expenses_today": 35000,
        },
    }


def send_device_command(
    face: str | None = None,
    sound: str | None = None,
    text: str | None = None,
    **_kwargs,
) -> dict:
    """Kirim perintah ke device (DEV STUB — tidak benar-benar mengirim).

    Argumen: face (str|None); sound (str|None); text (str|None).
    Minimal satu argumen harus diisi.
    """
    if face is None and sound is None and text is None:
        return {
            "success": False,
            "type": "device_command",
            "error": "Minimal salah satu dari face/sound/text harus diisi.",
        }
    return {
        "success": True,
        "type": "device_command",
        "stub": True,
        "command": {"face": face, "sound": sound, "text": text},
    }


# ---------------------------------------------------------------------------
# The discoverable agent. ``adk web`` reads this symbol by name.
# ---------------------------------------------------------------------------

#: List of stub tools exposed in the dev UI. The order mirrors
#: ``app.agent.tool_factory.build_tools`` for parity.
_DEV_TOOLS = [
    create_task,
    create_expense,
    set_reminder,
    get_today_summary,
    send_device_command,
]


root_agent = Agent(
    name="taskbot_agent",
    model=settings.google_adk_model,
    description="Asisten Taskbot berbahasa Indonesia (mode dev/ADK Web).",
    instruction=INSTRUCTION,
    tools=_DEV_TOOLS,
)


__all__ = [
    "root_agent",
    "create_task",
    "create_expense",
    "set_reminder",
    "get_today_summary",
    "send_device_command",
]
