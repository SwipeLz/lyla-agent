from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api._rate_limit import login_rate_limiter
from app.auth.passwords import hash_password
from app.auth.session import session_store
from app.config import settings
from app.main import app as fastapi_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "dashboard_username", "admin")
    monkeypatch.setattr(
        settings, "dashboard_password_scrypt", hash_password("admin")
    )
    monkeypatch.setattr(settings, "cookie_secure", False)
    login_rate_limiter.reset()
    with TestClient(fastapi_app) as c:
        yield c


def test_login_correct_creds_returns_200_with_cookie(client):
    response = client.post(
        "/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "admin"
    assert "expires_at" in body
    assert "lyla_session" in response.cookies


def test_login_wrong_password_returns_401(client):
    response = client.post(
        "/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_login_wrong_username_returns_401(client):
    response = client.post(
        "/auth/login", json={"username": "root", "password": "admin"}
    )
    assert response.status_code == 401


def test_login_with_empty_scrypt_value_always_401(client, monkeypatch):
    monkeypatch.setattr(settings, "dashboard_password_scrypt", "")
    response = client.post(
        "/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert response.status_code == 401


def test_logout_clears_cookie(client):
    login = client.post(
        "/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert login.status_code == 200
    response = client.post("/auth/logout")
    assert response.status_code == 204
    me = client.get("/auth/me")
    assert me.status_code == 401


def test_me_without_cookie_returns_401(client):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_with_valid_cookie_returns_200(client):
    client.post("/auth/login", json={"username": "admin", "password": "admin"})
    response = client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["username"] == "admin"


def test_login_cookie_secure_flag_when_setting_true(client, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)
    response = client.post(
        "/auth/login", json={"username": "admin", "password": "admin"}
    )
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert "Secure" in set_cookie
    session_store.revoke(response.cookies.get("lyla_session", ""))
