from __future__ import annotations

import io
import wave

from app.audio._seam import ConfigurationError, SynthesisResult
from app.config import settings


def _silent_wav(sample_rate: int, duration_ms: int = 100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_frames = max(1, int(sample_rate * duration_ms / 1000))
        wf.writeframes(b"\x00\x00" * num_frames)
    return buf.getvalue()


def synthesize_text(text: str) -> SynthesisResult:
    if settings.audio_tts_mode != "fake":
        raise ConfigurationError(
            f"Unsupported AUDIO_TTS_MODE={settings.audio_tts_mode!r}; "
            "only 'fake' is supported in Phase 10."
        )
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


__all__ = ["synthesize_text"]
