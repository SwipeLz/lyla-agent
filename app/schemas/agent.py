"""Pydantic schemas for the `POST /agent/text` endpoint.

These schemas enforce request validation at the FastAPI boundary so the
Agent Runtime never sees blank text, malformed user IDs, or other shapes
that would force defensive checks downstream.

Deviation from Requirement 5.1 (deliberate, design-document aligned)
-------------------------------------------------------------------
Requirement 5.1 nominally lists ``user_id: int`` and ``device_id: int |
None``. In practice every Phase 2/3 model that the agent runtime touches
(:class:`app.models.user.User`, :class:`app.models.device.Device`) uses
**string UUID** primary keys, and the rest of the stack — service layer,
tool wrappers, log service, runtime — already takes string IDs. Keeping
``int`` here would force every caller to either string-coerce on the way
in or fail every existence lookup (an integer literal would never match a
UUID string column). The design document's pseudocode in `design.md`
("`AgentTextRequest`" definition) also uses ``str`` for both fields.

We therefore declare ``user_id: str`` and ``device_id: str | None`` to
match the real data and the rest of the codebase. The semantic of the
requirement (validate, return 404 on unknown ids) is preserved.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class AgentTextRequest(BaseModel):
    """Request body for `POST /agent/text`.

    See module docstring for the rationale behind ``user_id: str`` and
    ``device_id: str | None`` (deviation from Requirement 5.1, aligned
    with design.md and the rest of the system that uses UUID strings).
    """

    user_id: str
    device_id: str | None = None
    text: str = Field(min_length=1)
    timezone: str | None = None

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, v: str) -> str:
        # Requirement 5.2: empty or whitespace-only text must be rejected
        # with HTTP 422 before the Agent Runtime is invoked. Raising
        # ValueError lets Pydantic surface this as a 422 validation error.
        if not v.strip():
            raise ValueError("text tidak boleh kosong")
        return v


class AgentTextResponse(BaseModel):
    """Response body for `POST /agent/text`.

    Mirrors the public contract from Requirement 6.3: `reply` is the
    agent's natural-language reply, `actions` is the ordered list of
    Tool Result Dicts produced during the invocation, and
    `device_feedback` is the most recent successful `send_device_command`
    Tool Result Dict, or `None`.
    """

    reply: str
    actions: list[dict]
    device_feedback: dict | None
