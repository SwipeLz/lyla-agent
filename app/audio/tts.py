from __future__ import annotations

import io
import wave
from threading import Lock

from app.audio._seam import ConfigurationError, SynthesisResult
from app.config import settings


_gemini_provider = None
_gemini_provider_lock = Lock()


def _silent_wav(sample_rate: int, duration_ms: int = 100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_frames = max(1, int(sample_rate * duration_ms / 1000))
        wf.writeframes(b"\x00\x00" * num_frames)
    return buf.getvalue()


def _get_gemini_provider():
    global _gemini_provider
    with _gemini_provider_lock:
        if _gemini_provider is None:
            from app.audio.tts_gemini import GeminiTtsProvider

            _gemini_provider = GeminiTtsProvider(
                model=settings.audio_tts_provider_model,
                voice=settings.audio_tts_voice,
                api_key=settings.google_api_key,
            )
    return _gemini_provider


def synthesize_text(text: str) -> SynthesisResult:
    mode = settings.audio_tts_mode
    if mode == "fake":
        audio_bytes = _silent_wav(settings.fake_tts_sample_rate)
        return SynthesisResult(
            mode="fake",
            content_type="audio/wav",
            audio_bytes=audio_bytes,
            text=text,
            metadata={
                "sample_rate": settings.fake_tts_sample_rate,
                "format": settings.fake_tts_format,
            },
        )
    if mode == "gemini":
        return _get_gemini_provider().synthesize(text)
    raise ConfigurationError(
        f"Unsupported AUDIO_TTS_MODE={mode!r}; expected 'fake' or 'gemini'."
    )


__all__ = ["synthesize_text"]
