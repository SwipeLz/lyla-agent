from __future__ import annotations

from fastapi.testclient import TestClient

from app.audio.tts_cache import tts_cache
from app.main import app


def test_protocol_header_on_audio_endpoint_404():
    client = TestClient(app)
    response = client.post(
        "/agent/audio",
        data={"user_id": "nonexistent"},
        files={"file": ("voice.wav", b"x" * 32, "audio/wav")},
    )
    assert response.headers.get("X-Lyla-Protocol") == "1"


def test_protocol_header_on_audio_tts_endpoint_404():
    tts_cache.clear()
    client = TestClient(app)
    response = client.get("/agent/audio/missing/tts")
    assert response.status_code == 404
    assert response.headers.get("X-Lyla-Protocol") == "1"


def test_protocol_header_on_audio_tts_endpoint_200():
    tts_cache.clear()
    log_id = "header-check-id"
    tts_cache.put(log_id, b"audio", "audio/wav")
    client = TestClient(app)
    response = client.get(f"/agent/audio/{log_id}/tts")
    assert response.status_code == 200
    assert response.headers.get("X-Lyla-Protocol") == "1"
    tts_cache.clear()


def test_no_protocol_header_on_unrelated_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert "X-Lyla-Protocol" not in response.headers
