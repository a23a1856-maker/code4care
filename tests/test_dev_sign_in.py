"""Development sign-in: one click for local use, and never available elsewhere."""
from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from tests.helpers import FakeEmailer, csrf_token


def _app_for(settings, tmp_path, environment: str):
    from app import db
    from app.main import create_app

    local = dataclasses.replace(
        settings, environment=environment, database_path=str(tmp_path / f"{environment}.db")
    )
    app = create_app(local)
    app.state.emailer = FakeEmailer()
    conn = db.connect(local.database_path)
    tenant_id = db.create_tenant(conn, "Farmasi Pembangunan")
    user = db.create_user(
        conn, tenant_id, "dev@farmasi.my", "Registered user", verified=True, is_owner=True
    )
    conn.close()
    return app, user


def test_the_login_page_has_no_shortcut_in_testing(client):
    page = client.get("/login")
    assert 'data-dev-sign-in="true"' not in page.text
    response = client.post(
        "/dev/login",
        data={"email": "dev@farmasi.my", "csrf_token": csrf_token(page.text)},
    )
    assert response.status_code == 404
    assert client.cookies.get("c4c_session") in (None, "")


def test_the_shortcut_does_not_exist_in_production(settings, tmp_path):
    app, user = _app_for(settings, tmp_path, "production")
    with TestClient(app, base_url="https://testserver") as prod:
        page = prod.get("/login")
        assert 'data-dev-sign-in="true"' not in page.text
        response = prod.post(
            "/dev/login", data={"email": user["email"], "csrf_token": csrf_token(page.text)}
        )
        assert response.status_code == 404
        assert prod.cookies.get("c4c_session") in (None, "")


def test_one_click_sign_in_in_development(settings, tmp_path):
    app, user = _app_for(settings, tmp_path, "development")
    with TestClient(app) as dev:
        page = dev.get("/login")
        assert 'data-dev-sign-in="true"' in page.text
        assert user["email"] in page.text

        response = dev.post(
            "/dev/login",
            data={"email": user["email"], "csrf_token": csrf_token(page.text)},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert dev.cookies.get("c4c_session")

        # No second factor in development, and every feature page works.
        assert dev.get("/").status_code == 200
        assert dev.get("/scan").status_code == 200

        conn_actions = dev.get("/usage")
        assert conn_actions.status_code == 200
        assert "auth.sign_in" in conn_actions.text


def test_development_shows_the_magic_link_instead_of_sending_it(settings, tmp_path):
    app, user = _app_for(settings, tmp_path, "development")
    with TestClient(app) as dev:
        page = dev.get("/login")
        sent = dev.post(
            "/login", data={"email": user["email"], "csrf_token": csrf_token(page.text)}
        )
        assert sent.status_code == 200
        assert 'data-dev-magic-link="true"' in sent.text
        assert "/auth/magic?token=" in sent.text


def test_unknown_development_account_says_what_to_do(settings, tmp_path):
    app, _user = _app_for(settings, tmp_path, "development")
    with TestClient(app) as dev:
        page = dev.get("/login")
        response = dev.post(
            "/dev/login",
            data={"email": "nobody@farmasi.my", "csrf_token": csrf_token(page.text)},
        )
        assert response.status_code == 404
        assert "scripts.seed_demo" in response.text
