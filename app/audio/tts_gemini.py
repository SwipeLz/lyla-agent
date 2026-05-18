"""Gemini TTS provider (Phase 11).

Implements ``TtsProvider`` Protocol from ``app.audio._seam``. The Gemini
SDK import is deferred to inside the method body, mirroring
``stt_gemini.py`` and ``app.agent.runtime._run_real``. The Gemini TTS
preview models emit raw PCM; this provider wraps the bytes in a
standard 24 kHz mono WAV header so callers can stream the result
directly to a player without further decoding.
"""
from __future__ import annotations

import io
import wave

from app.audio._seam import ConfigurationError, SynthesisResult


_PCM_SAMPLE_RATE = 24000
_PCM_CHANNELS = 1
_PCM_SAMPLE_WIDTH = 2


def _wrap_pcm_to_wav(
    pcm: bytes,
    *,
    rate: int = _PCM_SAMPLE_RATE,
    channels: int = _PCM_CHANNELS,
    sample_width: int = _PCM_SAMPLE_WIDTH,
) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


class GeminiTtsProvider:
    def __init__(self, model: str, voice: str, api_key: str) -> None:
        if not api_key:
            raise ConfigurationError(
                "Gemini TTS requires GOOGLE_API_KEY; set it in .env."
            )
        self._model = model
        self._voice = voice
        self._api_key = api_key

    def synthesize(self, text: str) -> SynthesisResult:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._api_key)
        response = client.models.generate_content(
            model=self._model,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=self._voice,
                        )
                    )
                ),
            ),
        )

        try:
            pcm = response.candidates[0].content.parts[0].inline_data.data
        except (IndexError, AttributeError) as exc:
            raise RuntimeError(
                "Gemini TTS response did not contain audio data."
            ) from exc

        if not pcm:
            raise RuntimeError("Gemini TTS returned empty audio data.")

        wav_bytes = _wrap_pcm_to_wav(pcm)
        return SynthesisResult(
            mode="gemini",
            content_type="audio/wav",
            audio_bytes=wav_bytes,
            text=text,
            metadata={
                "model": self._model,
                "voice": self._voice,
                "sample_rate": _PCM_SAMPLE_RATE,
                "channels": _PCM_CHANNELS,
                "sample_width": _PCM_SAMPLE_WIDTH,
            },
        )


__all__ = ["GeminiTtsProvider"]
