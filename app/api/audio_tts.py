"""GET /agent/audio/{log_id}/tts — binary TTS fetch endpoint (Phase 11b).

Returns the synthesized audio bytes for a voice command log id.
Cache is populated by ``app/api/audio.py::post_agent_audio`` when
``directive.audio_code == "fallback_tts"`` and TTS mode is real.

Cache miss / expired → 404. Phase 10 default (fake TTS) never populates
the cache, so this endpoint always returns 404 in fake mode — that's
correct: fallback_tts only triggers a real synthesis when ``audio_tts_mode
== "gemini"``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from app.audio.tts_cache import tts_cache

router = APIRouter(tags=["Agent"])


@router.get("/agent/audio/{log_id}/tts")
async def get_tts_audio(log_id: str) -> Response:
    """Stream cached TTS bytes for ``log_id`` or return 404."""
    entry = tts_cache.get(log_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TTS audio not available or cache entry expired",
        )
    audio_bytes, content_type = entry
    return Response(content=audio_bytes, media_type=content_type)
