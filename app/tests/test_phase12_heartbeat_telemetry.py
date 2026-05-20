from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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


@pytest.fixture
def client(shared_db_session, monkeypatch):
    def _override_get_db():
        try:
            yield shared_db_session
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(settings, "device_api_token", "esp-token-1234")
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def seed_device(shared_db_session):
    user = User(
        id=str(uuid4()),
        name="Demo",
        email=f"demo-{uuid4()}@taskbot.local",
        whatsapp_number=None,
    )
    shared_db_session.add(user)
    shared_db_session.commit()
    device = Device(
        id=str(uuid4()),
        user_id=user.id,
        device_code="TASKBOT-DEMO-001",
        name="Demo Device",
        status=DeviceStatus.OFFLINE,
        api_token="tk_live_demo",
    )
    shared_db_session.add(device)
    shared_db_session.commit()
    return device


def _heartbeat(client, device_code, body):
    return client.post(
        f"/devices/{device_code}/status",
        json=body,
        headers={"X-Device-Token": "esp-token-1234"},
    )


def test_heartbeat_without_telemetry_unchanged(client, seed_device, shared_db_session):
    response = _heartbeat(client, seed_device.device_code, {"status": "online"})
    assert response.status_code == 200
    shared_db_session.refresh(seed_device)
    assert seed_device.status == "online"
    assert seed_device.firmware_version is None
    assert seed_device.wifi_rssi_dbm is None


def test_heartbeat_with_full_telemetry_persists(client, seed_device, shared_db_session):
    response = _heartbeat(
        client,
        seed_device.device_code,
        {
            "status": "online",
            "firmware_version": "0.1.0",
            "wifi_rssi_dbm": -55,
            "battery_pct": 80,
            "free_heap_bytes": 200000,
        },
    )
    assert response.status_code == 200
    shared_db_session.refresh(seed_device)
    assert seed_device.firmware_version == "0.1.0"
    assert seed_device.wifi_rssi_dbm == -55
    assert seed_device.battery_pct == 80
    assert seed_device.free_heap_bytes == 200000


def test_heartbeat_overwrites_previous_telemetry(client, seed_device, shared_db_session):
    _heartbeat(
        client,
        seed_device.device_code,
        {"status": "online", "battery_pct": 80},
    )
    _heartbeat(
        client,
        seed_device.device_code,
        {"status": "online", "battery_pct": 30},
    )
    shared_db_session.refresh(seed_device)
    assert seed_device.battery_pct == 30
