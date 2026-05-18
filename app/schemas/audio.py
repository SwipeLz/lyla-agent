"""Pydantic schemas for the Phase 10 audio endpoint.

`AgentAudioResponse` inherits from `AgentTextResponse` so the
`reply`/`actions`/`device_feedback` contract has one source of truth and
cannot drift between text and audio paths.

Phase 10 ESP extension adds `directive` — a server-classified packet
that tells ESP32 firmware which pre-recorded audio file to play, which
face animation to show, and what to put on the OLED. ESP firmware MUST
match `directive.audio_code` exactly (no regex on `reply`).
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.agent import AgentTextResponse


class AudioMetadataOut(BaseModel):
    filename: str
    content_type: str
    size_bytes: int


class TranscriptionInfoOut(BaseModel):
    text: str
    mode: str
    duration_ms: int | None = None
    confidence: float | None = None


class FakeTTSInfoOut(BaseModel):
    mode: str
    available: bool
    content_type: str


class DirectiveOut(BaseModel):
    """Server-classified ESP playback directive.

    `audio_code` enumerates pre-recorded files on the ESP32 SD card.
    `fetch_url` is reserved for Phase 11 binary TTS streaming and is
    always `null` in Phase 10.
    """

    audio_code: str
    face: str
    screen_text: str | None = None
    fetch_url: str | None = None


class AgentAudioResponse(AgentTextResponse):
    transcription: TranscriptionInfoOut
    audio: AudioMetadataOut
    tts: FakeTTSInfoOut
    directive: DirectiveOut


__all__ = [
    "AudioMetadataOut",
    "TranscriptionInfoOut",
    "FakeTTSInfoOut",
    "DirectiveOut",
    "AgentAudioResponse",
]
