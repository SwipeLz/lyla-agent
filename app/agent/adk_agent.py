"""Google ADK agent builder for ``taskbot_agent``.

This module is the *only* place in :mod:`app.agent` that imports
``google.adk``. It is deliberately **not** imported from
``app/agent/__init__.py`` so that the fake-agent code path
(``agent_mode == "fake"``) and the test suite remain hermetic and never
load the Google ADK SDK.

The single public symbol is :func:`build_taskbot_agent`, which returns a
configured :class:`google.adk.agents.Agent` named ``taskbot_agent``. The
agent is built **without** an ``output_schema`` because setting
``output_schema`` historically disabled tool use on Gemini 2.x models;
the structured response shape (``AgentRunResult``) is assembled in
``app.agent.runtime`` from the event stream instead. Even on newer
models such as ``gemini-3-flash-preview`` we keep this contract so the
runtime stays model-agnostic.

The Indonesian-language system instruction enforces the device-friendly
response style required by the spec: a single short sentence, no tool
names or JSON leaking to the user, and an explicit clarification ask
when key data (amounts, dates) is missing.
"""
from __future__ import annotations

from typing import Any

from google.adk.agents import Agent

#: System instruction (Bahasa Indonesia) shown to the LLM. Constrains
#: replies to one short sentence suitable for a small device screen and
#: prohibits leaking tool/JSON details to the end user.
INSTRUCTION = """\
Kamu adalah Taskbot, asisten mahasiswa berbahasa Indonesia.
Aturan:
- Jawab maksimal SATU kalimat singkat (<= 20 kata) untuk perangkat layar kecil.
- Jangan mengarang data: jika informasi penting (jumlah, tanggal) hilang, minta klarifikasi.
- Untuk mencatat tugas/pengeluaran/reminder, panggil tool yang sesuai dan rangkum hasil dalam satu kalimat.
- Jangan menyebut nama tool atau format JSON ke pengguna.

Aturan konversi nilai uang (selalu kirim ke tool sebagai bilangan bulat
dalam satuan rupiah penuh, bukan shorthand):
- "10k", "10rb", "10 ribu" -> 10000
- "10jt", "10 juta" -> 10000000
- "Rp 10.000", "10.000", "Rp10.000" -> 10000 (di Indonesia titik adalah
  pemisah ribuan, BUKAN desimal)
- "10000", "Rp 10000" -> 10000
- Tolak nilai non-positif atau ambigu (mis. "sekitar 10") dengan minta
  klarifikasi sebelum memanggil tool.
"""


def build_taskbot_agent(
    *,
    model: str,
    tools: list[Any],
    instruction: str | None = None,
) -> Agent:
    """Construct the single ``taskbot_agent`` Google ADK agent.

    Args:
        model: The Gemini model identifier to use (e.g. the value of
            ``settings.google_adk_model``).
        tools: The list of ADK-friendly callables produced by
            :func:`app.agent.tool_factory.build_tools` for one request.
            The list MUST contain exactly the five Tool Surface tools
            (``create_task``, ``create_expense``, ``set_reminder``,
            ``get_today_summary``, ``send_device_command``); enforcement
            of this invariant lives in the tool factory and its tests.
        instruction: Optional override for the system instruction. When
            ``None`` the static ``INSTRUCTION`` constant is used. The
            runtime injects a per-request "now" block in front of
            ``INSTRUCTION`` so the LLM can resolve relative phrases like
            "2 menit lagi" against an actual clock instead of a model-
            internal guess.

    Returns:
        A :class:`google.adk.agents.Agent` instance named
        ``taskbot_agent`` configured with the Indonesian system
        instruction and the provided tools. No ``output_schema`` is set.
    """
    return Agent(
        name="taskbot_agent",
        model=model,
        description="Asisten Taskbot berbahasa Indonesia.",
        instruction=instruction if instruction is not None else INSTRUCTION,
        tools=tools,
    )


__all__ = ["INSTRUCTION", "build_taskbot_agent"]
