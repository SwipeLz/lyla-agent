"""Pydantic schemas for the Phase 10 audio endpoint.

`AgentAudioResponse` inherits from `AgentTextResponse` so the
`reply`/`actions`/`device_feedback` contract has one source of truth and
cannot drift between text and audio paths.
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


class AgentAudioResponse(AgentTextResponse):
    transcription: TranscriptionInfoOut
    audio: AudioMetadataOut
    tts: FakeTTSInfoOut


__all__ = [
    "AudioMetadataOut",
    "TranscriptionInfoOut",
    "FakeTTSInfoOut",
    "AgentAudioResponse",
]
