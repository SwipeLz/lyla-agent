from __future__ import annotations

from app.audio._seam import ConfigurationError, TranscriptionResult
from app.config import settings


def transcribe_audio(
    file_bytes: bytes,
    filename: str,
    content_type: str | None = None,
) -> TranscriptionResult:
    if settings.audio_stt_mode != "fake":
        raise ConfigurationError(
            f"Unsupported AUDIO_STT_MODE={settings.audio_stt_mode!r}; "
            "only 'fake' is supported in Phase 10."
        )
    return TranscriptionResult(
        text=settings.fake_stt_transcript,
        mode="fake",
        duration_ms=None,
        confidence=None,
        metadata={
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(file_bytes),
        },
    )


__all__ = ["transcribe_audio"]
