"""Manual smoke-test CLI for the Audio Backend (Phase 10).

Usage:
    python -m scripts.run_agent_audio path/to/audio.wav \
        [--user-id UUID] [--device-id UUID]

Resolves ``user_id`` from ``--user-id`` or env ``TASKBOT_USER_ID``,
``device_id`` from ``--device-id`` or env ``TASKBOT_DEVICE_ID``. Reads
the audio file once into memory, runs validation, fake STT, the shared
agent helper, and fake TTS, then prints the resulting
:class:`app.schemas.audio.AgentAudioResponse` JSON to stdout.

Hermetic by design: never opens an HTTP client, never spins up uvicorn,
never persists the audio bytes. Only the transcript text reaches
``VoiceCommandLog`` (via the shared helper).
"""
from __future__ import annotations

import argparse
import asyncio
import mimetypes
import os
import sys
from pathlib import Path

from app.api._agent_helpers import process_agent_text_command
from app.audio._seam import ConfigurationError
from app.audio.stt import transcribe_audio
from app.audio.tts import synthesize_text
from app.config import settings
from app.db import SessionLocal
from app.schemas.audio import (
    AgentAudioResponse,
    AudioMetadataOut,
    FakeTTSInfoOut,
    TranscriptionInfoOut,
)
from app.utils.audio_validation import AudioValidationError, validate_audio


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.run_agent_audio",
        description="Run the audio pipeline against a single audio file.",
    )
    parser.add_argument("audio_path", help="Path to a .wav/.mp3/.webm/.m4a file.")
    parser.add_argument(
        "--user-id",
        default=os.environ.get("TASKBOT_USER_ID"),
        help="User UUID (defaults to env TASKBOT_USER_ID).",
    )
    parser.add_argument(
        "--device-id",
        default=os.environ.get("TASKBOT_DEVICE_ID"),
        help="Optional device UUID (defaults to env TASKBOT_DEVICE_ID).",
    )
    return parser


async def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.user_id:
        print(
            "error: --user-id (or TASKBOT_USER_ID) is required",
            file=sys.stderr,
        )
        return 2

    audio_path = Path(args.audio_path)
    if not audio_path.is_file():
        print(f"error: file not found: {audio_path}", file=sys.stderr)
        return 2

    file_bytes = audio_path.read_bytes()
    content_type, _ = mimetypes.guess_type(str(audio_path))

    try:
        metadata = validate_audio(
            file_bytes=file_bytes,
            filename=audio_path.name,
            content_type=content_type,
            max_mb=settings.max_audio_upload_mb,
        )
    except AudioValidationError as exc:
        print(f"error: validation failed: {exc}", file=sys.stderr)
        return 1

    try:
        transcription = transcribe_audio(
            file_bytes=file_bytes,
            filename=metadata.filename,
            content_type=metadata.content_type,
        )
    except ConfigurationError as exc:
        print(f"error: STT misconfigured: {exc}", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        result = await process_agent_text_command(
            db,
            user_id=args.user_id,
            text=transcription.text,
            device_id=args.device_id or None,
            timezone=settings.timezone,
        )
    finally:
        db.close()

    try:
        tts_result = synthesize_text(transcription.text)
        tts_info = FakeTTSInfoOut(
            mode=tts_result.mode,
            available=True,
            content_type=tts_result.content_type,
        )
    except ConfigurationError as exc:
        print(f"warning: TTS misconfigured: {exc}", file=sys.stderr)
        tts_info = FakeTTSInfoOut(
            mode="fake",
            available=False,
            content_type="audio/wav",
        )

    response = AgentAudioResponse(
        reply=result.reply,
        actions=result.actions,
        device_feedback=result.device_feedback,
        transcription=TranscriptionInfoOut(
            text=transcription.text,
            mode=transcription.mode,
            duration_ms=transcription.duration_ms,
            confidence=transcription.confidence,
        ),
        audio=AudioMetadataOut(
            filename=metadata.filename,
            content_type=metadata.content_type,
            size_bytes=metadata.size_bytes,
        ),
        tts=tts_info,
    )

    print(response.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
