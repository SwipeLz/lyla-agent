"""Endpoint tests for ``POST /agent/audio`` (Phase 10).

Mirrors the test infrastructure in ``test_agent_text_endpoint.py``: a
``StaticPool`` SQLite engine shared between the test thread and the
TestClient worker thread, plus a recorded stub for the agent runtime
that the helper invokes. The runtime is patched at
``app.api._agent_helpers.run_text`` because the audio handler calls
the shared helper rather than the original ``app.api.agent`` import.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.result import AgentRunResult
from app.db import Base, get_db
from app.main import app as fastapi_app
import app.models  # noqa: F401
from app.models import Device, User, VoiceCommandLog
from app.models.constants import DeviceStatus
from app.config import settings


@pytest.fixture
def shared_db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(shared_db_session, monkeypatch):
    def _override_get_db():
        try:
            yield shared_db_session
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = _override_get_db

    async def _stub_run_text(db, *, user_id, device_id, text, timezone):
        return AgentRunResult(
            reply=f"reply for {text}",
            actions=[{"success": True, "type": "task", "id": "stub-1"}],
            device_feedback=None,
            status="success",
        )

    monkeypatch.setattr("app.api._agent_helpers.run_text", _stub_run_text)

    with TestClient(fastapi_app) as c:
        yield c

    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def seeded_user_and_device(shared_db_session):
    user = User(
        id=str(uuid4()),
        name="Audio Test",
        email=f"audio-{uuid4()}@example.com",
        whatsapp_number=None,
    )
    shared_db_session.add(user)
    shared_db_session.commit()

    device = Device(
        id=str(uuid4()),
        user_id=user.id,
        name="Audio Device",
        device_code=f"AUDIO-{uuid4().hex[:8]}",
        status=DeviceStatus.ONLINE,
    )
    shared_db_session.add(device)
    shared_db_session.commit()

    return user, device


def _wav_bytes() -> bytes:
    return b"RIFF\x00\x00\x00\x00WAVEfmt placeholder"


def test_happy_path_returns_200_with_full_response_shape(
    client, seeded_user_and_device, shared_db_session
) -> None:
    user, device = seeded_user_and_device

    response = client.post(
        "/agent/audio",
        data={
            "user_id": user.id,
            "device_id": device.id,
            "timezone": "Asia/Jakarta",
        },
        files={"file": ("voice.wav", _wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert "reply" in body
    assert isinstance(body["reply"], str) and body["reply"]
    assert isinstance(body["actions"], list) and len(body["actions"]) == 1
    assert "device_feedback" in body

    assert body["transcription"]["mode"] == "fake"
    assert body["transcription"]["text"] == settings.fake_stt_transcript

    assert body["audio"]["filename"] == "voice.wav"
    assert body["audio"]["content_type"] == "audio/wav"
    assert body["audio"]["size_bytes"] == len(_wav_bytes())

    assert body["tts"]["mode"] == "fake"
    assert body["tts"]["available"] is True
    assert body["tts"]["content_type"] == "audio/wav"


def test_voice_command_log_uses_transcribed_text(
    client, seeded_user_and_device, shared_db_session
) -> None:
    user, device = seeded_user_and_device

    response = client.post(
        "/agent/audio",
        data={"user_id": user.id, "device_id": device.id},
        files={"file": ("x.wav", _wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 200

    logs = shared_db_session.query(VoiceCommandLog).filter(
        VoiceCommandLog.user_id == user.id
    ).all()
    assert len(logs) == 1
    assert logs[0].input_text == settings.fake_stt_transcript
    assert logs[0].status == "success"


def test_unknown_user_returns_404_with_no_log(
    client, shared_db_session
) -> None:
    response = client.post(
        "/agent/audio",
        data={"user_id": str(uuid4())},
        files={"file": ("x.wav", _wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 404
    assert shared_db_session.query(VoiceCommandLog).count() == 0


def test_unknown_device_returns_404_with_no_log(
    client, seeded_user_and_device, shared_db_session
) -> None:
    user, _ = seeded_user_and_device
    response = client.post(
        "/agent/audio",
        data={"user_id": user.id, "device_id": str(uuid4())},
        files={"file": ("x.wav", _wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 404
    assert shared_db_session.query(VoiceCommandLog).count() == 0


def test_empty_file_rejected_400(
    client, seeded_user_and_device, shared_db_session
) -> None:
    user, _ = seeded_user_and_device
    response = client.post(
        "/agent/audio",
        data={"user_id": user.id},
        files={"file": ("x.wav", b"", "audio/wav")},
    )
    assert response.status_code == 400
    assert shared_db_session.query(VoiceCommandLog).count() == 0


def test_unsupported_extension_rejected_400(
    client, seeded_user_and_device
) -> None:
    user, _ = seeded_user_and_device
    response = client.post(
        "/agent/audio",
        data={"user_id": user.id},
        files={"file": ("x.flac", _wav_bytes(), "audio/flac")},
    )
    assert response.status_code == 400


def test_unsupported_content_type_rejected_400(
    client, seeded_user_and_device
) -> None:
    user, _ = seeded_user_and_device
    response = client.post(
        "/agent/audio",
        data={"user_id": user.id},
        files={"file": ("x.wav", _wav_bytes(), "text/plain")},
    )
    assert response.status_code == 400


def test_oversized_file_rejected_413(
    client, seeded_user_and_device, monkeypatch
) -> None:
    user, _ = seeded_user_and_device
    monkeypatch.setattr(settings, "max_audio_upload_mb", 1)
    big = b"x" * 1_500_000
    response = client.post(
        "/agent/audio",
        data={"user_id": user.id},
        files={"file": ("big.wav", big, "audio/wav")},
    )
    assert response.status_code == 413


def test_only_one_log_row_per_request(
    client, seeded_user_and_device, shared_db_session
) -> None:
    user, device = seeded_user_and_device
    response = client.post(
        "/agent/audio",
        data={"user_id": user.id, "device_id": device.id},
        files={"file": ("x.wav", _wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 200
    assert shared_db_session.query(VoiceCommandLog).count() == 1


def test_inherited_response_fields_present(
    client, seeded_user_and_device
) -> None:
    user, _ = seeded_user_and_device
    response = client.post(
        "/agent/audio",
        data={"user_id": user.id},
        files={"file": ("x.wav", _wav_bytes(), "audio/wav")},
    )
    body = response.json()
    for key in ("reply", "actions", "device_feedback", "transcription", "audio", "tts"):
        assert key in body, f"missing field {key} in response: {body}"
