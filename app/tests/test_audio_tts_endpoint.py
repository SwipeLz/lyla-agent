from __future__ import annotations

from fastapi.testclient import TestClient

from app.audio.tts_cache import tts_cache
from app.main import app


def test_get_tts_cache_hit_returns_audio_bytes():
    tts_cache.clear()
    log_id = "test-log-id-001"
    audio_bytes = b"RIFFxxxxWAVEfmt fake_audio_payload"
    tts_cache.put(log_id, audio_bytes, "audio/wav")

    client = TestClient(app)
    response = client.get(f"/agent/audio/{log_id}/tts")

    assert response.status_code == 200
    assert response.content == audio_bytes
    assert response.headers["content-type"] == "audio/wav"
    tts_cache.clear()


def test_get_tts_cache_miss_returns_404():
    tts_cache.clear()
    client = TestClient(app)
    response = client.get("/agent/audio/nonexistent-id/tts")
    assert response.status_code == 404
    body = response.json()
    assert "detail" in body
    assert "TTS audio not available" in body["detail"]


def test_get_tts_with_mp3_content_type():
    tts_cache.clear()
    log_id = "test-log-mp3"
    audio_bytes = b"fake_mp3_payload"
    tts_cache.put(log_id, audio_bytes, "audio/mpeg")

    client = TestClient(app)
    response = client.get(f"/agent/audio/{log_id}/tts")

    assert response.status_code == 200
    assert response.content == audio_bytes
    assert response.headers["content-type"] == "audio/mpeg"
    tts_cache.clear()
