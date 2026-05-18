from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ConfigurationError(Exception):
    """Raised when an unsupported audio mode is configured.

    Phase 10 only supports `fake` for `AUDIO_STT_MODE` and `AUDIO_TTS_MODE`;
    any other value triggers this error so misconfiguration fails loud and
    early instead of silently degrading to a real-provider call.
    """


@dataclass
class TranscriptionResult:
    text: str
    mode: str
    duration_ms: int | None = None
    confidence: float | None = None
    metadata: dict | None = None


@dataclass
class SynthesisResult:
    mode: str
    content_type: str
    audio_bytes: bytes | None
    text: str
    metadata: dict | None = None


class SttProvider(Protocol):
    def transcribe(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str | None,
    ) -> TranscriptionResult: ...


class TtsProvider(Protocol):
    def synthesize(self, text: str) -> SynthesisResult: ...


__all__ = [
    "ConfigurationError",
    "TranscriptionResult",
    "SynthesisResult",
    "SttProvider",
    "TtsProvider",
]
