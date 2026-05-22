"""Agent Runtime dispatcher: ``select_mode`` and ``run_text``.

This module is the public entry point for the Agent Runtime. Two callers
matter:

- :mod:`app.api.agent` (``POST /agent/text``) — invokes
  :func:`run_text` once per HTTP request.
- :mod:`scripts.run_agent_text` — the manual smoke-test CLI.

Mode selection is centralised in :func:`select_mode`, which encodes the
table from Property AR5 (Requirements 3.3, 3.4): an explicit
``settings.agent_mode`` always wins; otherwise the presence of a
``GOOGLE_API_KEY`` decides between the real and fake runners.

Hermeticity contract
--------------------

This module MUST NOT import ``google.adk.*`` or ``google.genai`` at
module top level. The runtime is imported even when
``agent_mode == "fake"`` (e.g. by the FastAPI app on startup, by the
test suite, by the CLI), and pulling in the Google SDK there would
defeat Property AR6 (Fake Agent Hermeticity, Requirements 3.2/3.5/16.2/16.3)
and break CI when ``google-adk`` is unavailable. The Google imports
therefore live *inside* :func:`_run_real`, which is only ever called
when ``select_mode`` returns ``"real"``.

The :func:`_run_real` body follows the design pseudocode verbatim:
build a fresh :class:`InMemorySessionService` per request, use a random
``session_id`` (so requests do not bleed state at the MVP stage),
iterate ``runner.run_async(...)``, harvest ``function_response.response``
payloads from each event into ``actions``, and pick up the final reply
when ``event.is_final_response()`` fires.

Exception policy
----------------

:func:`_run_real` does **not** catch exceptions broadly. The API layer
(:mod:`app.api.agent`) is responsible for converting an unhandled
exception into a 500 response and persisting an error
``VoiceCommandLog`` row (Requirement 6.6). Letting exceptions
propagate keeps the runtime decoupled from HTTP status concerns.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.agent.fake import _run_fake
from app.agent.result import AgentRunResult, _pick_device_feedback
from app.agent.tool_factory import build_tools
from app.config import settings as default_settings


def select_mode(settings: Any) -> str:
    """Map a settings object to the Agent Runtime mode.

    Implements the Property AR5 table (Requirements 3.3, 3.4):

    1. ``settings.agent_mode == "real"`` → ``"real"``.
    2. ``settings.agent_mode == "fake"`` → ``"fake"``.
    3. ``settings.agent_mode == ""`` and ``settings.google_api_key`` is
       non-empty → ``"real"``.
    4. Otherwise → ``"fake"``.

    Any other value of ``settings.agent_mode`` (e.g. an unrecognised
    string) falls through to ``"fake"``. AR5 only routes to ``"real"``
    via the ``google_api_key`` fallback when ``agent_mode`` is exactly
    ``""``, so a misconfigured override defaults to the safe (hermetic)
    mode rather than silently calling Gemini.
    """
    mode = getattr(settings, "agent_mode", "") or ""
    if mode == "real":
        return "real"
    if mode == "fake":
        return "fake"
    if mode == "" and (getattr(settings, "google_api_key", "") or ""):
        return "real"
    return "fake"


async def run_text(
    db,
    *,
    user_id,
    device_id,
    text: str,
    timezone: str | None,
) -> AgentRunResult:
    """Run the Agent Runtime against ``text`` and return an ``AgentRunResult``.

    Builds the per-request Tool Surface via
    :func:`app.agent.tool_factory.build_tools`, then dispatches to either
    :func:`_run_real` (Google ADK) or :func:`_run_fake` based on
    :func:`select_mode`. Both branches return an
    :class:`AgentRunResult` with the same shape, so callers do not need
    to know which mode ran.

    Args:
        db: SQLAlchemy session bound for the lifetime of this request.
        user_id: Resolved user identifier (already validated by the API
            layer for ``POST /agent/text``).
        device_id: Optional resolved device identifier; ``None`` means
            "no paired device", in which case ``send_device_command``
            short-circuits inside the tool factory.
        text: The user's raw text command, already validated as
            non-blank by the caller.
        timezone: IANA timezone string (e.g. ``"Asia/Jakarta"``); the
            runtime forwards it to the chosen runner. Currently neither
            runner alters business logic based on it, but the parameter
            is kept on the signature so future work (date parsing,
            "hari ini" semantics) can wire it through without an API
            break.
    """
    tools = build_tools(db, user_id, device_id)
    mode = select_mode(default_settings)
    if mode == "real":
        return await _run_real(tools=tools, text=text, timezone=timezone)
    return await _run_fake(tools=tools, text=text, timezone=timezone)


async def _run_real(
    *,
    tools: list,
    text: str,
    timezone: str | None,
) -> AgentRunResult:
    """Run ``taskbot_agent`` via the real Google ADK ``Runner``.

    Imports of ``google.adk`` / ``google.genai`` and the agent builder
    are **deferred** to the function body so the module remains hermetic
    when ``agent_mode == "fake"`` (Requirement 3.2). Building the
    :class:`InMemorySessionService` and a fresh ``session_id`` per call
    isolates requests at the MVP stage; a shared session service can be
    promoted to ``app.state`` later without touching the call sites.

    The async generator returned by
    :meth:`google.adk.runners.Runner.run_async` yields events whose
    ``content.parts`` may include a ``function_response`` (for tool
    invocations) and/or ``text`` (for the model's reply). We collect
    every ``function_response.response`` into ``actions`` in invocation
    order and capture the model's final reply when
    :meth:`Event.is_final_response` returns ``True`` — exactly per the
    design pseudocode.

    Exceptions raised by the Google SDK or any tool callable are
    intentionally not caught here; the API layer wraps them
    (Requirement 6.6).
    """
    import os
    from datetime import datetime, timezone as _tz_module
    from zoneinfo import ZoneInfo

    if default_settings.google_api_key and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = default_settings.google_api_key

    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from app.agent.adk_agent import INSTRUCTION, build_taskbot_agent

    tz_name = timezone or getattr(default_settings, "timezone", "Asia/Jakarta") or "Asia/Jakarta"
    try:
        local_tz = ZoneInfo(tz_name)
    except Exception:
        local_tz = ZoneInfo("Asia/Jakarta")
        tz_name = "Asia/Jakarta"

    now_utc_dt = datetime.now(tz=_tz_module.utc)
    now_local = now_utc_dt.astimezone(local_tz)
    offset = now_local.utcoffset() or _tz_module.utc.utcoffset(now_local)
    offset_hours = int(offset.total_seconds() // 3600) if offset else 0
    offset_label = f"UTC{offset_hours:+d}" if offset_hours else "UTC"

    now_block = (
        "Konteks waktu untuk percakapan ini (gunakan ini untuk menghitung "
        "ekspresi waktu relatif seperti 'sekarang', '5 menit lagi', "
        "'besok jam 9'):\n"
        f"- Sekarang lokal ({tz_name}, {offset_label}): "
        f"{now_local.isoformat(timespec='seconds')}\n"
        f"- Sekarang UTC: {now_utc_dt.isoformat(timespec='seconds')}\n"
        "Saat memanggil tool yang menerima argumen waktu (deadline_at, "
        "reminder_at, remind_at, spent_at), kirim string ISO 8601 LENGKAP "
        "DENGAN OFFSET ZONA WAKTU yang sama dengan 'Sekarang lokal' di atas, "
        f"misalnya '{now_local.isoformat(timespec='seconds')}'. "
        "Jangan pernah kirim waktu lebih awal dari 'Sekarang' karena tool "
        "akan menolak nilai tersebut.\n\n"
    )
    instruction = now_block + INSTRUCTION

    agent = build_taskbot_agent(
        model=default_settings.google_adk_model,
        tools=tools,
        instruction=instruction,
    )
    session_service = InMemorySessionService()
    session_id = str(uuid.uuid4())
    adk_user_id = "taskbot_user"
    await session_service.create_session(
        app_name="taskbot",
        user_id=adk_user_id,
        session_id=session_id,
    )
    runner = Runner(
        app_name="taskbot",
        agent=agent,
        session_service=session_service,
    )

    actions: list[dict] = []
    final_text = ""

    new_message = types.Content(role="user", parts=[types.Part(text=text)])
    async for event in runner.run_async(
        user_id=adk_user_id,
        session_id=session_id,
        new_message=new_message,
    ):
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) if content is not None else None
        for part in parts or []:
            function_response = getattr(part, "function_response", None)
            if function_response is None:
                continue
            response_payload = getattr(function_response, "response", None)
            if isinstance(response_payload, dict):
                actions.append(response_payload)

        if event.is_final_response():
            if content is not None and parts:
                final_text = "".join(
                    p.text for p in parts if getattr(p, "text", None)
                )

    return AgentRunResult(
        reply=final_text or "Maaf, aku belum bisa memproses itu.",
        actions=actions,
        device_feedback=_pick_device_feedback(actions),
        status="success",
    )


__all__ = ["select_mode", "run_text"]
