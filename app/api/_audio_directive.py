"""Directive classifier for the audio endpoint.

Maps the agent's `actions` list (Tool Result Dicts) into a stable
`DirectiveOut` payload that ESP32 firmware switches on. ESP firmware
matches `audio_code` against pre-recorded files on its SD card; it must
NOT pattern-match on `reply` text because Gemini phrasing varies.

Audio code namespace (must match files on ESP SD card):

    ok_expense        — create_expense succeeded
    ok_task           — create_task succeeded
    ok_reminder       — set_reminder succeeded
    ok_summary        — get_today_summary succeeded
    ok_generic        — fallback success (any other successful action)
    err_generic       — at least one action failed
    fallback_tts      — no actions returned; agent gave a text-only reply
                        and the firmware should request TTS audio
                        (fetch_url is null in Phase 10; planned Phase 11)
"""
from __future__ import annotations

from app.schemas.audio import DirectiveOut

_TYPE_TO_CODE: dict[str, tuple[str, str]] = {
    "expense": ("ok_expense", "happy"),
    "task": ("ok_task", "happy"),
    "reminder": ("ok_reminder", "happy"),
    "summary": ("ok_summary", "neutral"),
}

_SCREEN_TEXT_LIMIT = 60


def _truncate_for_screen(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = " ".join(text.split())
    if len(cleaned) <= _SCREEN_TEXT_LIMIT:
        return cleaned
    return cleaned[: _SCREEN_TEXT_LIMIT - 1].rstrip() + "\u2026"


def classify_directive(
    actions: list[dict],
    reply: str,
) -> DirectiveOut:
    """Return the ESP playback directive for one agent invocation."""
    if not actions:
        return DirectiveOut(
            audio_code="fallback_tts",
            face="thinking",
            screen_text=_truncate_for_screen(reply),
            fetch_url=None,
        )

    has_failure = any(not a.get("success") for a in actions)
    if has_failure:
        return DirectiveOut(
            audio_code="err_generic",
            face="sad",
            screen_text=_truncate_for_screen(reply),
            fetch_url=None,
        )

    for action in actions:
        if not action.get("success"):
            continue
        action_type = action.get("type")
        if isinstance(action_type, str) and action_type in _TYPE_TO_CODE:
            code, face = _TYPE_TO_CODE[action_type]
            return DirectiveOut(
                audio_code=code,
                face=face,
                screen_text=_truncate_for_screen(reply),
                fetch_url=None,
            )

    return DirectiveOut(
        audio_code="ok_generic",
        face="happy",
        screen_text=_truncate_for_screen(reply),
        fetch_url=None,
    )


__all__ = ["classify_directive"]
