"""One-off probe: cek apakah API key Gemini di .env bisa generate TTS audio."""
from __future__ import annotations

import io
import sys
import time
import wave

from app.config import settings


def _wrap_pcm_to_wav(pcm: bytes, *, channels: int = 1, rate: int = 24000, sample_width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def main() -> int:
    api_key = settings.google_api_key
    if not api_key:
        print("error: GOOGLE_API_KEY belum diset di .env", file=sys.stderr)
        return 2

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        print(f"error: import google-genai gagal: {exc}", file=sys.stderr)
        return 2

    text = "Halo, ini Lyla. Tugas algoritma kamu sudah dicatat untuk besok pagi."
    candidates = [
        "gemini-3.1-flash-tts-preview",
        "gemini-2.5-flash-tts",
        "gemini-2.5-flash-lite-preview-tts",
        "gemini-2.5-pro-tts",
    ]

    client = genai.Client(api_key=api_key)

    for model in candidates:
        print(f"--> mencoba model: {model}")
        t0 = time.time()
        try:
            response = client.models.generate_content(
                model=model,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Leda",
                            )
                        )
                    ),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  GAGAL: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue

        elapsed = time.time() - t0
        try:
            part = response.candidates[0].content.parts[0]
            pcm = part.inline_data.data
        except Exception as exc:  # noqa: BLE001
            print(f"  shape error: {exc}", file=sys.stderr)
            continue

        if not pcm:
            print("  response kosong (no inline_data)", file=sys.stderr)
            continue

        wav_bytes = _wrap_pcm_to_wav(pcm)
        out_name = f"gemini_tts_probe_{model.replace('/', '_')}.wav"
        with open(out_name, "wb") as f:
            f.write(wav_bytes)

        print(f"  SUKSES dalam {elapsed:.2f}s; PCM={len(pcm)} bytes; WAV={len(wav_bytes)} bytes")
        print(f"  audio disimpan: {out_name}")
        print(f"  >>> API key kamu bisa pakai model {model}")
        return 0

    print("error: semua model TTS gagal", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
