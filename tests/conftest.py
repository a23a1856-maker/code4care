"""Shared fixtures for the CODE4CARE test suite."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from tests.helpers import (
    FakeEmailer,
    latest_message,
    magic_path,
    six_digit_code,
)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """A Settings object built from environment variables only (M0: reads .env)."""
    monkeypatch.setenv("APP_SECRET", "unit-test-secret-0123456789abcdef")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "code4care.db"))
    monkeypatch.setenv("MEDIA_PATH", str(tmp_path / "medicine-images"))
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("BASE_URL", "http://testserver")
    monkeypatch.setenv("EMAIL_API_KEY", "")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-google-secret")
    monkeypatch.setenv("PAYMENT_API_KEY", "")
    monkeypatch.setenv("PAYMENT_WEBHOOK_SECRET", "")
    from app.config import Settings

    return Settings.from_env()


@pytest.fixture
def app(settings):
    from app.main import create_app

    application = create_app(settings)
    application.state.emailer = FakeEmailer()
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def outbox(app):
    return app.state.emailer


@pytest.fixture
def world(app):
    """Two pharmacies (tenants) with one user per role, and their catalogues."""
    from app import db

    conn = db.connect(app.state.settings.database_path)
    farmasi_a = db.create_tenant(conn, "Farmasi Sihat A")
    farmasi_b = db.create_tenant(conn, "Farmasi Sihat B")

    users = {}
    for label, tenant_key, tenant_id, role, owner, verified in (
        ("owner_a", "a", farmasi_a, "Registered user", True, True),
        ("member_a", "a", farmasi_a, "Registered user", False, True),
        ("pharmacist_a", "a", farmasi_a, "Pharmacist/health care professional", False, True),
        ("guest_a", "a", farmasi_a, "Guest User", False, True),
        ("admin_a", "a", farmasi_a, "System Administrator", False, True),
        ("owner_b", "b", farmasi_b, "Registered user", True, True),
        ("unverified_a", "a", farmasi_a, "Registered user", False, False),
    ):
        email = f"{label}@farmasi.example"
        users[label] = db.create_user(
            conn,
            tenant_id=tenant_id,
            email=email,
            role=role,
            verified=verified,
            is_owner=owner,
        )
        users[label]["email"] = email
        users[label]["role"] = role

    data = {
        "conn": conn,
        "tenants": {"a": farmasi_a, "b": farmasi_b},
        "users": users,
        "medicines": {
            "a": db.list_medicines(conn, farmasi_a),
            "b": db.list_medicines(conn, farmasi_b),
        },
    }
    yield data
    conn.close()


class SignedIn:
    """The result of a full sign-in: what the browser would now hold."""

    def __init__(self, client, email, token, csrf):
        self.client = client
        self.email = email
        self.token = token
        self.csrf = csrf


def _csrf_from(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "form must carry a CSRF token"
    return match.group(1)


def sign_in(client, email: str, *, code: str | None = None) -> SignedIn:
    """Sign in through email magic link, submitting the 2FA code when asked."""
    page = client.get("/login")
    csrf = _csrf_from(page.text)
    response = client.post(
        "/login", data={"email": email, "csrf_token": csrf}, follow_redirects=False
    )
    assert response.status_code == 200, response.text

    outbox = client.app.state.emailer
    path = magic_path(latest_message(outbox, email))
    response = client.get(path, follow_redirects=False)
    assert response.status_code in (303, 302, 307)

    if response.headers["location"].startswith("/login/2fa"):
        code_page = client.get("/login/2fa")
        csrf = _csrf_from(code_page.text)
        one_time = code or six_digit_code(latest_message(outbox, email))
        response = client.post(
            "/login/2fa",
            data={"code": one_time, "csrf_token": csrf},
            follow_redirects=False,
        )
        assert response.status_code in (303, 302), response.text

    cookie = client.cookies.get("c4c_session")
    assert cookie, "sign-in must set a session cookie"
    # From now on the session carries its own CSRF token; take it from a page.
    home = client.get("/")
    csrf = _csrf_from(home.text)
    return SignedIn(client, email, cookie, csrf)
