"""Property AR7 — Audio module hermeticity.

Mirrors AR6 (Fake Agent hermeticity, see test_agent_fake_hermeticity.py).
Importing app.audio.* and exercising the fake STT/TTS callables MUST NOT
load any provider SDK or google.adk.* into sys.modules.
"""

from __future__ import annotations

import importlib
import sys

from hypothesis import given, settings as hyp_settings, strategies as st


_FORBIDDEN_MODULES: tuple[str, ...] = (
    "google.cloud.speech",
    "google.cloud.texttospeech",
    "google.adk.runners",
    "google.adk.agents",
    "google.adk.sessions",
    "openai",
    "whisper",
    "elevenlabs",
    "deepgram",
    "assemblyai",
)


def _purge_forbidden_from_sys_modules() -> None:
    for forbidden in _FORBIDDEN_MODULES:
        for mod in list(sys.modules):
            if mod == forbidden or mod.startswith(forbidden + "."):
                sys.modules.pop(mod, None)
    for mod in list(sys.modules):
        if mod == "google.adk" or mod.startswith("google.adk."):
            sys.modules.pop(mod, None)


def _audio_modules_fresh_import() -> None:
    for mod in ("app.audio.stt", "app.audio.tts", "app.audio._seam", "app.audio"):
        sys.modules.pop(mod, None)
    importlib.import_module("app.audio._seam")
    importlib.import_module("app.audio.stt")
    importlib.import_module("app.audio.tts")


def test_audio_modules_do_not_import_forbidden_sdks() -> None:
    _purge_forbidden_from_sys_modules()
    _audio_modules_fresh_import()
    leaked = [m for m in _FORBIDDEN_MODULES if m in sys.modules]
    assert leaked == [], (
        f"app.audio.* leaked forbidden modules into sys.modules: {leaked}. "
        "Property AR7 (audio module hermeticity) violated."
    )
    assert "google.adk" not in sys.modules, (
        "app.audio.* leaked google.adk; AR7 forbids ADK imports here."
    )


@hyp_settings(max_examples=20, deadline=None)
@given(text=st.text(min_size=1, max_size=80))
def test_property_ar7_fake_stt_call_hermeticity(text: str) -> None:
    _purge_forbidden_from_sys_modules()
    from app.audio.stt import transcribe_audio

    transcribe_audio(
        file_bytes=b"\x00" * 16,
        filename="x.wav",
        content_type="audio/wav",
    )
    leaked = [m for m in _FORBIDDEN_MODULES if m in sys.modules]
    assert leaked == [], (
        f"transcribe_audio leaked forbidden modules: {leaked}. "
        f"text input was {text!r}. AR7 violated."
    )


@hyp_settings(max_examples=20, deadline=None)
@given(text=st.text(min_size=1, max_size=80))
def test_property_ar7_fake_tts_call_hermeticity(text: str) -> None:
    _purge_forbidden_from_sys_modules()
    from app.audio.tts import synthesize_text

    synthesize_text(text)
    leaked = [m for m in _FORBIDDEN_MODULES if m in sys.modules]
    assert leaked == [], (
        f"synthesize_text leaked forbidden modules: {leaked}. "
        f"text input was {text!r}. AR7 violated."
    )
