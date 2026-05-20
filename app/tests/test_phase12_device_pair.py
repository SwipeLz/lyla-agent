from __future__ import annotations

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
from app.models import User


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
    monkeypatch.setattr(settings, "mvp_user_email", "demo@taskbot.local")
    monkeypatch.setattr(settings, "base_url", "http://test.local:8765")
    login_rate_limiter.reset()
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def seed_demo_user(shared_db_session):
    user = User(
        id=str(uuid4()),
        name="Demo",
        email="demo@taskbot.local",
        whatsapp_number=None,
    )
    shared_db_session.add(user)
    shared_db_session.commit()
    return user


def _login(client):
    return client.post(
        "/auth/login", json={"username": "admin", "password": "admin"}
    )


def test_pair_without_session_returns_401(client, seed_demo_user):
    response = client.post("/devices/pair", json={"name": "Lyla Demo Unit"})
    assert response.status_code == 401


def test_pair_with_session_returns_201_and_valid_config_json(
    client, seed_demo_user
):
    _login(client)
    response = client.post("/devices/pair", json={"name": "Lyla Demo Unit"})
    assert response.status_code == 201
    body = response.json()
    assert body["device_code"].startswith("TASKBOT-")
    assert len(body["device_code"]) == len("TASKBOT-") + 8
    assert body["api_token"].startswith("tk_live_")
    config = body["config_json"]
    assert config["user_id"] == seed_demo_user.id
    assert config["device_id"] == body["device_id"]
    assert config["device_code"] == body["device_code"]
    assert config["device_token"] == body["api_token"]
    assert config["base_url"] == "http://test.local:8765"
    assert config["wifi"] == {"ssid": "", "password": ""}
    assert config["firmware_version"] == "0.1.0"


def test_pair_when_demo_user_missing_returns_404(client):
    _login(client)
    response = client.post("/devices/pair", json={"name": "Lyla"})
    assert response.status_code == 404


def test_no_rotate_token_endpoint_exists(client, seed_demo_user):
    _login(client)
    pair = client.post("/devices/pair", json={"name": "Lyla Demo Unit"}).json()
    response = client.post(f"/devices/{pair['device_id']}/rotate-token")
    assert response.status_code == 404
