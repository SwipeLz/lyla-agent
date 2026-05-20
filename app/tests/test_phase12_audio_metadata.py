from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.result import AgentRunResult
from app.config import settings
from app.db import Base, get_db
from app.main import app as fastapi_app
from app.models import Device, User, VoiceCommandLog
from app.models.constants import DeviceStatus


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
    monkeypatch.setattr(settings, "require_device_token", False)

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
        name="Audio",
        email=f"audio-{uuid4()}@example.com",
        whatsapp_number=None,
    )
    shared_db_session.add(user)
    device = Device(
        id=str(uuid4()),
        user_id=user.id,
        device_code=f"dev-{uuid4().hex[:8]}",
        name="Demo",
        status=DeviceStatus.OFFLINE,
        api_token="tk_live_x",
    )
    shared_db_session.add(device)
    shared_db_session.commit()
    return user, device


def _wav_bytes() -> bytes:
    return (
        b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
        b"\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00"
        b"data\x00\x00\x00\x00"
    )


def _post_audio(client, user, device, **extra):
    files = {"file": ("voice.wav", _wav_bytes(), "audio/wav")}
    data = {
        "user_id": user.id,
        "device_id": device.id,
        "timezone": "Asia/Jakarta",
    }
    data.update(extra)
    return client.post("/agent/audio", data=data, files=files)


def _last_log(db) -> VoiceCommandLog:
    return (
        db.query(VoiceCommandLog)
        .order_by(VoiceCommandLog.created_at.desc())
        .first()
    )


def test_metadata_has_server_stage_timings_without_telemetry(
    client, seeded_user_and_device, shared_db_session
):
    user, device = seeded_user_and_device
    response = _post_audio(client, user, device)
    assert response.status_code == 200
    log = _last_log(shared_db_session)
    assert log.metadata_json is not None
    timings = log.metadata_json["stage_timings_ms"]
    assert timings["validate"] is not None
    assert timings["stt"] is not None
    assert timings["agent"] is not None
    assert timings["classify"] is not None
    client_block = log.metadata_json["client"]
    assert client_block == {
        "request_id": None,
        "firmware_version": None,
        "wifi_rssi_dbm": None,
        "battery_pct": None,
        "recording_duration_ms": None,
    }


def test_metadata_captures_client_telemetry(
    client, seeded_user_and_device, shared_db_session
):
    user, device = seeded_user_and_device
    response = _post_audio(
        client,
        user,
        device,
        client_request_id="req-1",
        firmware_version="0.1.0",
        wifi_rssi_dbm=-55,
        battery_pct=80,
        recording_duration_ms=3200,
    )
    assert response.status_code == 200
    log = _last_log(shared_db_session)
    client_block = log.metadata_json["client"]
    assert client_block["request_id"] == "req-1"
    assert client_block["firmware_version"] == "0.1.0"
    assert client_block["wifi_rssi_dbm"] == -55
    assert client_block["battery_pct"] == 80
    assert client_block["recording_duration_ms"] == 3200


def test_metadata_includes_audio_and_directive(
    client, seeded_user_and_device, shared_db_session
):
    user, device = seeded_user_and_device
    response = _post_audio(client, user, device)
    assert response.status_code == 200
    log = _last_log(shared_db_session)
    assert log.metadata_json["audio"]["filename"] == "voice.wav"
    assert log.metadata_json["audio"]["content_type"] == "audio/wav"
    assert log.metadata_json["directive"]["audio_code"] is not None


def test_response_shape_unchanged(client, seeded_user_and_device):
    user, device = seeded_user_and_device
    response = _post_audio(client, user, device)
    body = response.json()
    for key in ("reply", "actions", "device_feedback", "transcription", "audio", "tts", "directive"):
        assert key in body


def test_error_path_writes_metadata_with_error_layer(
    client, seeded_user_and_device, shared_db_session, monkeypatch
):
    user, device = seeded_user_and_device

    async def _boom(db, *, user_id, device_id, text, timezone):
        raise RuntimeError("agent boom")

    monkeypatch.setattr("app.api._agent_helpers.run_text", _boom)
    response = _post_audio(client, user, device)
    assert response.status_code == 500
    log = _last_log(shared_db_session)
    assert log.status == "error"
    assert log.metadata_json["error"]["layer"] == "agent"
