"""Phase 11a end-to-end latency measurement.

Generates a realistic Indonesian voice command via Gemini TTS, then
runs the full /agent/audio pipeline locally (in-process, real Gemini
calls) with per-stage timing so we know exactly where the time goes.

Output is markdown-friendly so the result can be pasted into a doc.
"""
from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from app.api._agent_helpers import process_agent_text_command
from app.api._audio_directive import classify_directive
from app.audio.stt import transcribe_audio
from app.audio.tts import synthesize_text
from app.config import settings
from app.db import SessionLocal
from app.utils.audio_validation import validate_audio


COMMAND = "Catat tugas matematika integral besok jam delapan pagi."
USER_ID = "9f58e349-63b2-4f30-8fce-277d8cc670d7"
DEVICE_ID = "34074323-28c8-459c-a005-f9d9b8d26ddb"


timings: dict[str, float] = {}


@contextmanager
def stage(name: str):
    t0 = time.perf_counter()
    yield
    timings[name] = time.perf_counter() - t0


def _generate_test_audio() -> Path:
    """Generate test audio via Gemini TTS and save to disk.

    We synthesize a realistic command sentence so the STT path has a
    meaningful workload (silent WAV produces hallucinated transcripts).
    """
    out = Path("test_command.wav")
    if out.exists():
        print(f"[fixture] reusing existing {out} ({out.stat().st_size} bytes)")
        return out

    print(f"[fixture] generating test audio via Gemini TTS for: {COMMAND!r}")
    with patch.object(settings, "audio_tts_mode", "gemini"):
        with stage("__fixture_tts"):
            result = synthesize_text(COMMAND)
    assert result.audio_bytes
    out.write_bytes(result.audio_bytes)
    print(f"[fixture] saved {len(result.audio_bytes)} bytes ({timings.pop('__fixture_tts'):.2f}s)")
    return out


async def measure() -> None:
    audio_path = _generate_test_audio()
    audio_bytes = audio_path.read_bytes()

    print()
    print("=" * 60)
    print(f"Pipeline measurement: AUDIO_STT_MODE=gemini AUDIO_TTS_MODE=gemini")
    print(f"Audio file: {audio_path} ({len(audio_bytes)} bytes)")
    print(f"Command spoken: {COMMAND!r}")
    print("=" * 60)
    print()

    stt_patch = patch.object(settings, "audio_stt_mode", "gemini")
    tts_patch = patch.object(settings, "audio_tts_mode", "gemini")
    stt_patch.start()
    tts_patch.start()

    try:
        with stage("validate"):
            metadata = validate_audio(
                file_bytes=audio_bytes,
                filename=audio_path.name,
                content_type="audio/wav",
                max_mb=settings.max_audio_upload_mb,
            )

        with stage("stt_gemini"):
            transcription = transcribe_audio(
                file_bytes=audio_bytes,
                filename=metadata.filename,
                content_type=metadata.content_type,
            )
        print(f"  transcript: {transcription.text!r}")

        db = SessionLocal()
        try:
            with stage("agent_gemini"):
                result = await process_agent_text_command(
                    db,
                    user_id=USER_ID,
                    text=transcription.text,
                    device_id=DEVICE_ID,
                    timezone="Asia/Jakarta",
                )
        finally:
            db.close()
        print(f"  reply: {result.reply!r}")
        print(f"  actions: {len(result.actions)} action(s)")

        with stage("classify"):
            directive = classify_directive(
                actions=result.actions,
                reply=result.reply,
            )
        print(f"  directive: audio_code={directive.audio_code!r} face={directive.face!r}")

        with stage("tts_gemini"):
            tts_result = synthesize_text(result.reply)
        print(f"  tts: {len(tts_result.audio_bytes or b'')} bytes WAV")
    finally:
        stt_patch.stop()
        tts_patch.stop()

    total = sum(timings.values())

    print()
    print("=" * 60)
    print("LATENCY BREAKDOWN")
    print("=" * 60)
    print(f"{'stage':<20} {'seconds':>10} {'percent':>10}")
    print("-" * 60)
    for name, secs in timings.items():
        pct = (secs / total * 100) if total > 0 else 0
        print(f"{name:<20} {secs:>10.3f} {pct:>9.1f}%")
    print("-" * 60)
    print(f"{'TOTAL':<20} {total:>10.3f}")
    print()
    print(f"Note: Without TTS (success path → ESP plays from SD card):")
    no_tts_total = total - timings.get("tts_gemini", 0)
    print(f"  effective latency: {no_tts_total:.3f}s")


if __name__ == "__main__":
    asyncio.run(measure())
