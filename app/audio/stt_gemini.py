"""Gemini multimodal STT provider (Phase 11).

Implements ``SttProvider`` Protocol from ``app.audio._seam``. The Gemini
SDK import is **deferred** to inside the method body so importing this
module does not pull ``google.genai`` into ``sys.modules``. AR7 covers
``_seam.py`` / ``stt.py`` / ``tts.py`` (the dispatchers); this real-
provider module is allowed to load the SDK lazily, mirroring the pattern
in ``app.agent.runtime._run_real``.
"""
from __future__ import annotations

from app.audio._seam import ConfigurationError, TranscriptionResult


_GEMINI_TRANSCRIBE_PROMPT = (
    "Transcribe the audio in Bahasa Indonesia. "
    "Output ONLY the literal transcript text, no commentary, no quotes, "
    "no formatting. If the audio is silent or unintelligible, output an "
    "empty string."
)


class GeminiSttProvider:
    def __init__(self, model: str, api_key: str, prompt: str | None = None) -> None:
        if not api_key:
            raise ConfigurationError(
                "Gemini STT requires GOOGLE_API_KEY; set it in .env."
            )
        self._model = model
        self._api_key = api_key
        self._prompt = prompt or _GEMINI_TRANSCRIBE_PROMPT

    def transcribe(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str | None,
    ) -> TranscriptionResult:
        from google import genai
        from google.genai import types

        mime_type = (content_type or "audio/wav").lower().strip()
        client = genai.Client(api_key=self._api_key)
        response = client.models.generate_content(
            model=self._model,
            contents=[
                self._prompt,
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
            ],
        )
        text = (response.text or "").strip()
        return TranscriptionResult(
            text=text,
            mode="gemini",
            duration_ms=None,
            confidence=None,
            metadata={
                "model": self._model,
                "filename": filename,
                "content_type": mime_type,
                "size_bytes": len(file_bytes),
            },
        )


__all__ = ["GeminiSttProvider"]
