"""Agent runtime result type.

Defines :class:`AgentRunResult`, the structured value returned by
``app.agent.runtime.run_text``. The dataclass intentionally only depends on
``dataclasses`` and ``typing`` so it can be imported in both the real (Google
ADK) and fake agent code paths without pulling in heavy SDKs.

Per the design document, ``device_feedback`` is the most recent successful
``send_device_command`` *Tool Result Dict* observed in ``actions`` — i.e. the
last entry whose ``type == "device_command"`` and ``success is True``. The
:func:`_pick_device_feedback` helper centralises this selection so callers
(``runtime._run_real`` and ``fake._run_fake``) build :class:`AgentRunResult`
consistently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentRunResult:
    """Result returned by an Agent Runtime invocation.

    Attributes:
        reply: The single-sentence Indonesian reply intended for the user.
        actions: Ordered list of Tool Result Dicts produced by the Phase 3
            tool wrappers during this invocation, in invocation order.
        device_feedback: The most recent successful ``send_device_command``
            Tool Result Dict from ``actions`` if any, otherwise ``None``.
        status: ``"success"`` or ``"error"``.
        error: Optional error message; non-``None`` only when ``status`` is
            ``"error"``.
    """

    reply: str
    actions: list[dict] = field(default_factory=list)
    device_feedback: dict | None = None
    status: str = "success"
    error: str | None = None


def _pick_device_feedback(actions: list[dict] | None) -> dict | None:
    """Return the last successful ``send_device_command`` action, or ``None``.

    Iterates ``actions`` from the end and returns the first entry that is a
    ``dict`` with ``type == "device_command"`` and ``success is True``. Returns
    ``None`` when ``actions`` is empty, ``None``, or contains no such entry.

    The strict ``is True`` check guards against truthy-but-non-bool values
    (e.g. ``1``, ``"yes"``) being treated as a successful device command.
    """
    if not actions:
        return None
    for entry in reversed(actions):
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "device_command" and entry.get("success") is True:
            return entry
    return None


__all__ = ["AgentRunResult", "_pick_device_feedback"]
