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
from app.models import Device, User
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


def _wav_bytes() -> bytes:
    return (
        b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
        b"\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00"
        b"data\x00\x00\x00\x00"
    )


@pytest.fixture
def seeded(shared_db_session):
    user = User(
        id=str(uuid4()),
        name="Demo",
        email=f"gate-{uuid4()}@taskbot.local",
        whatsapp_number=None,
    )
    shared_db_session.add(user)
    device = Device(
        id=str(uuid4()),
        user_id=user.id,
        device_code=f"TASKBOT-{uuid4().hex[:8].upper()}",
        name="Demo",
        status=DeviceStatus.OFFLINE,
        api_token="tk_live_paired_secret",
    )
    shared_db_session.add(device)
    shared_db_session.commit()
    return user, device


@pytest.fixture
def client_gate_on(shared_db_session, monkeypatch):
    def _override_get_db():
        try:
            yield shared_db_session
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(settings, "require_device_token", True)

    async def _stub_run_text(db, *, user_id, device_id, text, timezone):
        return AgentRunResult(
            reply="ok",
            actions=[],
            device_feedback=None,
            status="success",
        )

    monkeypatch.setattr("app.api._agent_helpers.run_text", _stub_run_text)
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()


def test_require_device_token_dep_blocks_missing_header(
    client_gate_on, shared_db_session, seeded
):
    from fastapi import FastAPI

    from app.api._auth_dependencies import require_device_token
    from fastapi import Depends

    sub = FastAPI()

    @sub.get("/probe")
    def probe(_: object = Depends(require_device_token)):
        return {"ok": True}

    sub.dependency_overrides[get_db] = lambda: (yield shared_db_session)

    with TestClient(sub) as c:
        no_header = c.get("/probe")
        assert no_header.status_code == 401
        bad = c.get("/probe", headers={"X-Device-Token": "wrong"})
        assert bad.status_code == 401
        good = c.get(
            "/probe", headers={"X-Device-Token": "tk_live_paired_secret"}
        )
        assert good.status_code == 200


def test_require_device_token_dep_returns_none_when_disabled(
    shared_db_session, seeded, monkeypatch
):
    from fastapi import FastAPI

    from app.api._auth_dependencies import require_device_token
    from fastapi import Depends

    monkeypatch.setattr(settings, "require_device_token", False)
    sub = FastAPI()

    @sub.get("/probe")
    def probe(_: object = Depends(require_device_token)):
        return {"ok": True}

    sub.dependency_overrides[get_db] = lambda: (yield shared_db_session)

    with TestClient(sub) as c:
        no_header = c.get("/probe")
        assert no_header.status_code == 200


def _post_audio(client, user_id, device_id, headers=None):
    files = {"file": ("voice.wav", _wav_bytes(), "audio/wav")}
    data = {
        "user_id": user_id,
        "device_id": device_id,
        "timezone": "Asia/Jakarta",
    }
    return client.post(
        "/agent/audio",
        data=data,
        files=files,
        headers=headers or {},
    )


def test_agent_audio_blocks_request_without_header(client_gate_on, seeded):
    user, device = seeded
    response = _post_audio(client_gate_on, user.id, device.id)
    assert response.status_code == 401
    assert response.json()["detail"] == "Device token required"


def test_agent_audio_blocks_request_with_invalid_header(client_gate_on, seeded):
    user, device = seeded
    response = _post_audio(
        client_gate_on,
        user.id,
        device.id,
        headers={"X-Device-Token": "tk_live_wrong"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid device token"


def test_agent_audio_accepts_request_with_valid_header(client_gate_on, seeded):
    user, device = seeded
    response = _post_audio(
        client_gate_on,
        user.id,
        device.id,
        headers={"X-Device-Token": "tk_live_paired_secret"},
    )
    assert response.status_code == 200


def test_tts_fetch_blocks_without_header(client_gate_on, seeded):
    response = client_gate_on.get(f"/agent/audio/{uuid4()}/tts")
    assert response.status_code == 401


def test_tts_fetch_with_valid_token_returns_404_when_cache_miss(
    client_gate_on, seeded
):
    response = client_gate_on.get(
        f"/agent/audio/{uuid4()}/tts",
        headers={"X-Device-Token": "tk_live_paired_secret"},
    )
    assert response.status_code == 404
