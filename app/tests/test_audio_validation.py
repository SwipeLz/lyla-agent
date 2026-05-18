from __future__ import annotations

import pytest

from app.utils.audio_validation import (
    AudioValidationError,
    validate_audio,
)


@pytest.mark.parametrize(
    "filename,content_type",
    [
        ("voice.wav", "audio/wav"),
        ("voice.wav", "audio/x-wav"),
        ("voice.mp3", "audio/mpeg"),
        ("voice.mp3", "audio/mp3"),
        ("voice.webm", "audio/webm"),
        ("voice.m4a", "audio/mp4"),
        ("voice.m4a", "audio/x-m4a"),
        ("voice.m4a", "audio/aac"),
        ("voice.wav", "application/octet-stream"),
        ("voice.wav", None),
    ],
)
def test_accept_valid_combinations(filename: str, content_type: str | None) -> None:
    metadata = validate_audio(
        file_bytes=b"\x00" * 32,
        filename=filename,
        content_type=content_type,
        max_mb=10,
    )
    assert metadata.filename == filename
    assert metadata.size_bytes == 32
    assert metadata.detected_extension == filename[filename.rfind(".") :]


def test_reject_unsupported_extension() -> None:
    with pytest.raises(AudioValidationError) as excinfo:
        validate_audio(
            file_bytes=b"\x00" * 32,
            filename="voice.flac",
            content_type="audio/flac",
            max_mb=10,
        )
    assert excinfo.value.status_code == 400


def test_reject_unsupported_content_type() -> None:
    with pytest.raises(AudioValidationError) as excinfo:
        validate_audio(
            file_bytes=b"\x00" * 32,
            filename="voice.wav",
            content_type="text/plain",
            max_mb=10,
        )
    assert excinfo.value.status_code == 400


def test_reject_empty_file() -> None:
    with pytest.raises(AudioValidationError) as excinfo:
        validate_audio(
            file_bytes=b"",
            filename="voice.wav",
            content_type="audio/wav",
            max_mb=10,
        )
    assert excinfo.value.status_code == 400


def test_reject_oversized_file() -> None:
    with pytest.raises(AudioValidationError) as excinfo:
        validate_audio(
            file_bytes=b"x" * 10_000_001,
            filename="voice.wav",
            content_type="audio/wav",
            max_mb=10,
        )
    assert excinfo.value.status_code == 413


@pytest.mark.parametrize("filename", [None, "", "   "])
def test_reject_missing_filename(filename: str | None) -> None:
    with pytest.raises(AudioValidationError) as excinfo:
        validate_audio(
            file_bytes=b"\x00" * 32,
            filename=filename,
            content_type="audio/wav",
            max_mb=10,
        )
    assert excinfo.value.status_code == 400


def test_size_bytes_matches_input_length() -> None:
    metadata = validate_audio(
        file_bytes=b"a" * 12345,
        filename="voice.wav",
        content_type="audio/wav",
        max_mb=10,
    )
    assert metadata.size_bytes == 12345
