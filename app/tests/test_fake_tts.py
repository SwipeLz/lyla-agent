from __future__ import annotations

import io
import wave

import pytest

from app.audio._seam import ConfigurationError, SynthesisResult
from app.audio.tts import synthesize_text
from app.config import settings


def test_returns_fake_synthesis_result() -> None:
    result = synthesize_text("halo dunia")
    assert isinstance(result, SynthesisResult)
    assert result.mode == "fake"
    assert result.content_type == "audio/wav"
    assert result.text == "halo dunia"
    assert isinstance(result.audio_bytes, bytes)


def test_audio_bytes_are_riff_wave() -> None:
    result = synthesize_text("test")
    assert result.audio_bytes is not None
    assert result.audio_bytes[:4] == b"RIFF"
    assert result.audio_bytes[8:12] == b"WAVE"


def test_audio_bytes_parseable_by_stdlib_wave() -> None:
    result = synthesize_text("test")
    assert result.audio_bytes is not None
    with wave.open(io.BytesIO(result.audio_bytes), "rb") as wf:
        assert wf.getframerate() == settings.fake_tts_sample_rate
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2


def test_deterministic() -> None:
    a = synthesize_text("hello")
    b = synthesize_text("hello")
    assert a == b


def test_unsupported_provider_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "audio_tts_mode", "elevenlabs")
    with pytest.raises(ConfigurationError) as excinfo:
        synthesize_text("hi")
    assert "elevenlabs" in str(excinfo.value)
