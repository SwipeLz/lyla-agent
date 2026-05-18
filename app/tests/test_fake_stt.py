from __future__ import annotations

import pytest

from app.audio._seam import ConfigurationError, TranscriptionResult
from app.audio.stt import transcribe_audio
from app.config import settings


def test_returns_canned_transcript_in_fake_mode() -> None:
    result = transcribe_audio(
        file_bytes=b"\x00" * 32,
        filename="voice.wav",
        content_type="audio/wav",
    )
    assert isinstance(result, TranscriptionResult)
    assert result.mode == "fake"
    assert result.text == settings.fake_stt_transcript


def test_honours_fake_stt_transcript_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "fake_stt_transcript", "halo dunia")
    result = transcribe_audio(
        file_bytes=b"\x00" * 32,
        filename="voice.wav",
        content_type="audio/wav",
    )
    assert result.text == "halo dunia"


def test_deterministic() -> None:
    a = transcribe_audio(
        file_bytes=b"\x01" * 32,
        filename="x.wav",
        content_type="audio/wav",
    )
    b = transcribe_audio(
        file_bytes=b"\x01" * 32,
        filename="x.wav",
        content_type="audio/wav",
    )
    assert a == b


def test_unsupported_real_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "audio_stt_mode", "real")
    with pytest.raises(ConfigurationError):
        transcribe_audio(b"\x00", "x.wav", "audio/wav")


def test_unsupported_provider_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "audio_stt_mode", "openai")
    with pytest.raises(ConfigurationError) as excinfo:
        transcribe_audio(b"\x00", "x.wav", "audio/wav")
    assert "openai" in str(excinfo.value)
