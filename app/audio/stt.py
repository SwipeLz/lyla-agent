from __future__ import annotations

from threading import Lock

from app.audio._seam import ConfigurationError, TranscriptionResult
from app.config import settings


_gemini_provider = None
_gemini_provider_lock = Lock()


def _get_gemini_provider():
    global _gemini_provider
    with _gemini_provider_lock:
        if _gemini_provider is None:
            from app.audio.stt_gemini import GeminiSttProvider

            _gemini_provider = GeminiSttProvider(
                model=settings.audio_stt_provider_model,
                api_key=settings.google_api_key,
            )
    return _gemini_provider


def transcribe_audio(
    file_bytes: bytes,
    filename: str,
    content_type: str | None = None,
) -> TranscriptionResult:
    mode = settings.audio_stt_mode
    if mode == "fake":
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
    if mode == "gemini":
        return _get_gemini_provider().transcribe(
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
        )
    raise ConfigurationError(
        f"Unsupported AUDIO_STT_MODE={mode!r}; expected 'fake' or 'gemini'."
    )


__all__ = ["transcribe_audio"]
