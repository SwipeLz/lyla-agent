"""Audio upload validation (Phase 10).

Pure-function validator for multipart audio uploads. No FastAPI imports
so it can be unit-tested with raw bytes. The endpoint handler converts
`AudioValidationError` into the appropriate HTTP response.

`MAX_AUDIO_UPLOAD_MB` is interpreted as decimal megabytes
(1 MB = 1_000_000 bytes).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".wav", ".mp3", ".webm", ".m4a"})

ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/webm",
        "audio/mp4",
        "audio/x-m4a",
        "audio/aac",
        "application/octet-stream",
    }
)


@dataclass
class AudioMetadata:
    filename: str
    content_type: str
    size_bytes: int
    detected_extension: str


class AudioValidationError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def validate_audio(
    file_bytes: bytes,
    filename: str | None,
    content_type: str | None,
    max_mb: int,
) -> AudioMetadata:
    if not isinstance(filename, str) or not filename.strip():
        raise AudioValidationError("missing filename", status_code=400)

    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise AudioValidationError(
            f"unsupported extension {extension!r}", status_code=400
        )

    resolved_content_type = (content_type or "").lower().strip()
    if resolved_content_type:
        if resolved_content_type not in ALLOWED_CONTENT_TYPES:
            raise AudioValidationError(
                f"unsupported content type {content_type!r}",
                status_code=400,
            )
    else:
        resolved_content_type = "application/octet-stream"

    if not file_bytes:
        raise AudioValidationError("empty file", status_code=400)

    max_bytes = max_mb * 1_000_000
    if len(file_bytes) > max_bytes:
        raise AudioValidationError(
            f"oversized file: {len(file_bytes)} > {max_bytes} bytes",
            status_code=413,
        )

    return AudioMetadata(
        filename=filename,
        content_type=resolved_content_type,
        size_bytes=len(file_bytes),
        detected_extension=extension,
    )


__all__ = [
    "ALLOWED_EXTENSIONS",
    "ALLOWED_CONTENT_TYPES",
    "AudioMetadata",
    "AudioValidationError",
    "validate_audio",
]
