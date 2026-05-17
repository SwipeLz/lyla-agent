"""Fake Agent runner for tests and CI.

This module is the hermetic alternative to the real Google ADK code path.
It is selected automatically when ``settings.agent_mode == "fake"`` (e.g.
when ``GOOGLE_API_KEY`` is unset) and is the primary path exercised by the
test suite. Crucially, this file MUST NOT import ``google.adk.*`` — doing
so would defeat the hermeticity property the design promises (Property
AR6) and break CI when the SDK is unavailable.

The Fake Agent does *not* call Gemini. It performs simple Indonesian
keyword detection on the user text and dispatches to one of the five Tool
Surface callables produced by :func:`app.agent.tool_factory.build_tools`.
Because it shares the very same per-request tool factory as the real
agent, side effects on the database and the *Tool Result Dicts* recorded
in :class:`AgentRunResult.actions` are byte-for-byte equivalent for the
inputs the Fake Agent supports (Requirement 3.6).

Detection rules
---------------

The check order is deliberate — earlier rules win, so more discriminating
signals come first:

1. **Expense** — text contains one of ``makan`` / ``beli`` / ``bayar``
   *and* a positive integer. The first integer found is used as the
   ``amount`` and the original text is stored as ``note``.
2. **Reminder** — text contains ``ingatkan`` or ``reminder``. The text is
   used as the reminder ``title``. ``remind_at`` is intentionally not
   supplied; the underlying wrapper will return a failure
   *Tool Result Dict* if validation rejects this, which is captured in
   ``actions`` as-is.
3. **Task** — text contains ``catat`` or ``tugas``. The text is used as
   the task ``title``. Placed before "summary" so phrases like
   ``catat tugas hari ini matematika`` are routed to a task and not to a
   summary lookup.
4. **Summary** — text contains ``ringkasan`` or ``hari ini``. Calls the
   no-argument ``get_today_summary`` tool.

If none of the rules match, the runner returns the canonical "I don't
understand" reply (Requirement 3.2 / design ``_run_fake`` paragraph).

The reply string is always a single short Indonesian sentence summarising
the outcome, suitable for a small device screen.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Iterable

from app.agent.result import AgentRunResult, _pick_device_feedback

# Pre-compiled patterns. ``\d+`` captures the first run of digits; we
# accept any positive integer because expenses are stored as ``int`` IDR.
_AMOUNT_RE = re.compile(r"\d+")

_EXPENSE_KEYWORDS: tuple[str, ...] = ("makan", "beli", "bayar")
_REMINDER_KEYWORDS: tuple[str, ...] = ("ingatkan", "reminder")
_TASK_KEYWORDS: tuple[str, ...] = ("catat", "tugas")
_SUMMARY_KEYWORDS: tuple[str, ...] = ("ringkasan", "hari ini")

_FALLBACK_REPLY = "Maaf, aku belum mengerti perintah itu."


def _contains_any(text_lower: str, keywords: Iterable[str]) -> bool:
    """Return True when any of ``keywords`` is a substring of ``text_lower``."""
    return any(kw in text_lower for kw in keywords)


def _tools_by_name(tools: list[Callable[..., Any]]) -> dict[str, Callable[..., Any]]:
    """Index the tool callables by their ``__name__`` attribute.

    The Per-Request Tool Factory sets ``__name__`` on each closure to the
    Tool Surface name (``create_task``, ``create_expense``, ``set_reminder``,
    ``get_today_summary``, ``send_device_command``). We rely on that here
    so the Fake Agent stays decoupled from the factory's internals.
    """
    return {getattr(t, "__name__", ""): t for t in tools}


def _reply_for_task(result: dict, title: str) -> str:
    if result.get("success") is True:
        return f"Tugas '{title.strip()}' tercatat."
    return f"Maaf, gagal mencatat tugas: {result.get('error', 'kesalahan tidak diketahui')}."


def _reply_for_expense(result: dict, amount: int) -> str:
    if result.get("success") is True:
        return f"Pengeluaran Rp{amount} tercatat."
    return f"Maaf, gagal mencatat pengeluaran: {result.get('error', 'kesalahan tidak diketahui')}."


def _reply_for_reminder(result: dict) -> str:
    if result.get("success") is True:
        return "Pengingat dipasang."
    return f"Maaf, gagal memasang pengingat: {result.get('error', 'kesalahan tidak diketahui')}."


def _reply_for_summary(result: dict) -> str:
    if result.get("success") is True:
        tasks = result.get("tasks_due_today", 0)
        total = result.get("total_expenses_today", 0)
        return f"Hari ini ada {tasks} tugas dan pengeluaran Rp{total}."
    return f"Maaf, gagal mengambil ringkasan: {result.get('error', 'kesalahan tidak diketahui')}."


async def _run_fake(
    *,
    tools: list[Callable[..., Any]],
    text: str,
    timezone: str | None,
) -> AgentRunResult:
    """Run the Fake Agent against ``text`` using ``tools``.

    Args:
        tools: The list returned by
            :func:`app.agent.tool_factory.build_tools` for this request.
            Each callable's ``__name__`` must be one of the five Tool
            Surface names.
        text: The user's raw input text (already validated as non-blank
            by the API layer).
        timezone: Currently unused by the Fake Agent — accepted to keep
            the signature aligned with ``_run_real`` so callers can
            ``await`` either uniformly.

    Returns:
        An :class:`AgentRunResult` whose ``actions`` contains zero or one
        Tool Result Dict (the Fake Agent dispatches at most one tool per
        invocation in this MVP), whose ``reply`` summarises the outcome
        in one Indonesian sentence, and whose ``status`` is always
        ``"success"`` because tool-level failures are surfaced via the
        captured Tool Result Dict, not by raising.
    """
    del timezone  # MVP: timezone is not used by the Fake Agent.

    text_lower = text.lower()
    tools_map = _tools_by_name(tools)
    actions: list[dict] = []

    # 1. Expense — strongest signal: a keyword AND a positive integer.
    if _contains_any(text_lower, _EXPENSE_KEYWORDS):
        amount_match = _AMOUNT_RE.search(text)
        create_expense = tools_map.get("create_expense")
        if amount_match is not None and create_expense is not None:
            amount = int(amount_match.group(0))
            result = create_expense(amount=amount, note=text)
            actions.append(result)
            return AgentRunResult(
                reply=_reply_for_expense(result, amount),
                actions=actions,
                device_feedback=_pick_device_feedback(actions),
                status="success",
            )

    # 2. Reminder — explicit keywords ``ingatkan`` / ``reminder``.
    if _contains_any(text_lower, _REMINDER_KEYWORDS):
        set_reminder = tools_map.get("set_reminder")
        if set_reminder is not None:
            result = set_reminder(title=text)
            actions.append(result)
            return AgentRunResult(
                reply=_reply_for_reminder(result),
                actions=actions,
                device_feedback=_pick_device_feedback(actions),
                status="success",
            )

    # 3. Task — ``catat`` / ``tugas``. Checked before "summary" so phrases
    #    like ``catat tugas hari ini matematika`` route to a task.
    if _contains_any(text_lower, _TASK_KEYWORDS):
        create_task = tools_map.get("create_task")
        if create_task is not None:
            result = create_task(title=text)
            actions.append(result)
            return AgentRunResult(
                reply=_reply_for_task(result, text),
                actions=actions,
                device_feedback=_pick_device_feedback(actions),
                status="success",
            )

    # 4. Summary — ``ringkasan`` / ``hari ini``.
    if _contains_any(text_lower, _SUMMARY_KEYWORDS):
        get_today_summary = tools_map.get("get_today_summary")
        if get_today_summary is not None:
            result = get_today_summary()
            actions.append(result)
            return AgentRunResult(
                reply=_reply_for_summary(result),
                actions=actions,
                device_feedback=_pick_device_feedback(actions),
                status="success",
            )

    # Fallback: no rule matched, or the matching tool is missing from the
    # provided tool list (defensive — should not happen with a real factory).
    return AgentRunResult(
        reply=_FALLBACK_REPLY,
        actions=[],
        device_feedback=None,
        status="success",
    )


__all__ = ["_run_fake"]
