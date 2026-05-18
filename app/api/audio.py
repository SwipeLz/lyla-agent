from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api._agent_helpers import process_agent_text_command
from app.audio._seam import ConfigurationError
from app.audio.stt import transcribe_audio
from app.audio.tts import synthesize_text
from app.config import settings
from app.db import get_db
from app.schemas.audio import (
    AgentAudioResponse,
    AudioMetadataOut,
    FakeTTSInfoOut,
    TranscriptionInfoOut,
)
from app.utils.audio_validation import AudioValidationError, validate_audio

router = APIRouter(tags=["Agent"])


@router.post("/agent/audio", response_model=AgentAudioResponse)
async def post_agent_audio(
    user_id: str = Form(...),
    device_id: str | None = Form(None),
    timezone: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> AgentAudioResponse:
    """Transcribe audio with fake STT and run the existing agent flow.

    Phase 10: hermetic-only. Validation → fake STT → shared agent helper
    → fake TTS metadata. Audio bytes are processed in memory and never
    persisted; only the transcript text is logged in `VoiceCommandLog`.
    """
    file_bytes = await file.read()

    try:
        metadata = validate_audio(
            file_bytes=file_bytes,
            filename=file.filename,
            content_type=file.content_type,
            max_mb=settings.max_audio_upload_mb,
        )
    except AudioValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    try:
        transcription = transcribe_audio(
            file_bytes=file_bytes,
            filename=metadata.filename,
            content_type=metadata.content_type,
        )
    except ConfigurationError:
        raise
    except Exception:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Audio transcription failed",
        )

    result = await process_agent_text_command(
        db,
        user_id=user_id,
        text=transcription.text,
        device_id=device_id,
        timezone=timezone,
    )

    try:
        tts_result = synthesize_text(transcription.text)
        tts_info = FakeTTSInfoOut(
            mode=tts_result.mode,
            available=True,
            content_type=tts_result.content_type,
        )
    except ConfigurationError:
        raise
    except Exception:  # noqa: BLE001
        tts_info = FakeTTSInfoOut(
            mode="fake",
            available=False,
            content_type="audio/wav",
        )

    return AgentAudioResponse(
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
