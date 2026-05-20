from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api._rate_limit import login_rate_limiter
from app.auth.passwords import hash_password
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
    monkeypatch.setattr(settings, "dashboard_username", "admin")
    monkeypatch.setattr(
        settings, "dashboard_password_scrypt", hash_password("admin")
    )
    monkeypatch.setattr(settings, "cookie_secure", False)
    login_rate_limiter.reset()
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def seeded(shared_db_session):
    user = User(
        id=str(uuid4()),
        name="Demo",
        email=f"obs-{uuid4()}@taskbot.local",
        whatsapp_number=None,
    )
    shared_db_session.add(user)
    device = Device(
        id=str(uuid4()),
        user_id=user.id,
        device_code=f"TASKBOT-{uuid4().hex[:8].upper()}",
        name="Demo",
        status=DeviceStatus.OFFLINE,
        api_token="tk_live_xx",
    )
    shared_db_session.add(device)
    shared_db_session.commit()
    return user, device


def _login(client):
    return client.post(
        "/auth/login", json={"username": "admin", "password": "admin"}
    )


def _add_log(
    db,
    user,
    device,
    *,
    status_value="success",
    audio_code="ok_task",
    total_ms=1000,
    age_seconds=10,
):
    now = datetime.now(tz=timezone.utc)
    received = now - timedelta(seconds=age_seconds)
    sent = received + timedelta(milliseconds=total_ms)
    log = VoiceCommandLog(
        id=str(uuid4()),
        user_id=user.id,
        device_id=device.id,
        input_text="catat tugas",
        parsed_actions=[],
        response_text="ok",
        status=status_value,
        request_received_at=received,
        response_sent_at=sent,
        metadata_json={
            "stage_timings_ms": {
                "validate": 1,
                "stt": 100,
                "agent": 200,
                "classify": 1,
                "tts": 50,
            },
            "directive": {
                "audio_code": audio_code,
                "face": "happy",
                "screen_text": "ok",
            },
            "audio": {
                "filename": "v.wav",
                "size_bytes": 1024,
                "content_type": "audio/wav",
            },
            "client": {
                "request_id": "req-1",
                "firmware_version": "0.1.0",
                "wifi_rssi_dbm": -55,
                "battery_pct": 80,
                "recording_duration_ms": 3000,
            },
            "transcription": {"mode": "fake", "duration_ms": None},
            "tts": {"mode": "fake", "available": True, "content_type": "audio/wav"},
            "error": None,
        },
    )
    db.add(log)
    db.commit()
    return log


def test_trace_without_session_returns_401(client, seeded, shared_db_session):
    user, device = seeded
    log = _add_log(shared_db_session, user, device)
    response = client.get(f"/observability/trace/{log.id}")
    assert response.status_code == 401


def test_trace_with_session_returns_full_structure(
    client, seeded, shared_db_session
):
    user, device = seeded
    log = _add_log(shared_db_session, user, device)
    _login(client)
    response = client.get(f"/observability/trace/{log.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == log.id
    assert body["status"] == "success"
    assert body["stage_timings"]["agent"] == 200
    assert body["client"]["firmware_version"] == "0.1.0"
    assert body["directive"]["audio_code"] == "ok_task"


def test_trace_unknown_log_returns_404(client):
    _login(client)
    response = client.get(f"/observability/trace/{uuid4()}")
    assert response.status_code == 404


def test_recent_default_returns_newest_first(client, seeded, shared_db_session):
    user, device = seeded
    for i in range(3):
        _add_log(shared_db_session, user, device, age_seconds=i)
    _login(client)
    response = client.get("/observability/recent?limit=10")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3


def test_recent_with_status_filter(client, seeded, shared_db_session):
    user, device = seeded
    _add_log(shared_db_session, user, device, status_value="success")
    _add_log(shared_db_session, user, device, status_value="error")
    _login(client)
    response = client.get("/observability/recent?status=error")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "error"


def test_stats_returns_numeric_percentiles(client, seeded, shared_db_session):
    user, device = seeded
    for i in range(5):
        _add_log(
            shared_db_session,
            user,
            device,
            total_ms=100 * (i + 1),
        )
    _login(client)
    response = client.get("/observability/stats?window=1h")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 5
    assert body["success_count"] == 5
    assert body["p50_ms"] is not None
    assert body["p95_ms"] is not None
    assert body["top_audio_codes"][0]["code"] == "ok_task"


def test_devices_returns_array_without_api_token(
    client, seeded, shared_db_session
):
    _login(client)
    response = client.get("/observability/devices")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert "api_token" not in body[0]
    assert body[0]["is_online"] in (True, False)


def test_devices_without_session_returns_401(client, seeded):
    response = client.get("/observability/devices")
    assert response.status_code == 401
