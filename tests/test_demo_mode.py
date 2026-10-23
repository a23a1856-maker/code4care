"""Demo boxes: DEMO_SIGN_IN shows the one-click panel, DEMO_AUTO_SIGN_IN skips it.

A deployed demo should behave exactly like the local one, so both switches work in
`production` as well — but only when the machine sets them. Neither is on by default.
"""
from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from tests.helpers import FakeEmailer, csrf_token

DEMO_OWNER = "pemilik@farmasi-demo.my"
DEMO_PHARMACIST = "farmasi@farmasi-demo.my"


def _demo_app(settings, tmp_path, *, accounts: bool = True, **flags):
    from app import db
    from app.main import create_app

    prod = dataclasses.replace(
        settings,
        environment="production",
        database_path=str(tmp_path / "demo.db"),
        **flags,
    )
    app = create_app(prod)
    app.state.emailer = FakeEmailer()
    if accounts:
        conn = db.connect(prod.database_path)
        tenant_id = db.create_tenant(conn, "Farmasi Demo")
        db.create_user(
            conn, tenant_id, DEMO_OWNER, "Registered user", verified=True, is_owner=True
        )
        db.create_user(
            conn, tenant_id, DEMO_PHARMACIST, "Pharmacist/health care professional"
        )
        conn.close()
    return app


def test_a_plain_production_box_still_has_the_real_sign_in_page(settings, tmp_path):
    app = _demo_app(settings, tmp_path)
    with TestClient(app, base_url="https://testserver") as prod:
        page = prod.get("/login")

        assert page.status_code == 200
        assert 'data-dev-sign-in="true"' not in page.text
        assert prod.get("/scan", follow_redirects=False).status_code == 303


def test_demo_sign_in_shows_the_panel_in_production(settings, tmp_path):
    app = _demo_app(settings, tmp_path, demo_sign_in=True)
    with TestClient(app, base_url="https://testserver") as prod:
        page = prod.get("/login")

        assert 'data-dev-sign-in="true"' in page.text
        assert DEMO_OWNER in page.text

        response = prod.post(
            "/dev/login",
            data={"email": DEMO_OWNER, "csrf_token": csrf_token(page.text)},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert prod.cookies.get("c4c_session")


def test_demo_auto_sign_in_skips_the_sign_in_page(settings, tmp_path):
    app = _demo_app(settings, tmp_path, demo_auto_sign_in=True)
    with TestClient(app, base_url="https://testserver") as prod:
        home = prod.get("/", follow_redirects=False)

        assert home.status_code == 200
        assert DEMO_OWNER in home.text
        assert prod.cookies.get("c4c_session"), "the page must have signed the demo owner in"
        # Every feature page opens without a sign-in step.
        for path in ("/scan", "/history", "/favourites", "/team", "/usage", "/settings"):
            assert prod.get(path).status_code == 200, path


def test_logging_in_as_someone_else_survives_the_demo(settings, tmp_path):
    app = _demo_app(settings, tmp_path, demo_sign_in=True, demo_auto_sign_in=True)
    with TestClient(app, base_url="https://testserver") as prod:
        prod.get("/")  # the demo owner is signed in
        page = prod.get("/login")
        switched = prod.post(
            "/dev/login",
            data={"email": DEMO_PHARMACIST, "csrf_token": csrf_token(page.text)},
            follow_redirects=False,
        )
        assert switched.status_code == 303

        home = prod.get("/")

        assert DEMO_PHARMACIST in home.text
        assert DEMO_OWNER not in home.text


def test_the_sign_in_page_itself_never_signs_anyone_in(settings, tmp_path):
    app = _demo_app(settings, tmp_path, demo_auto_sign_in=True)
    with TestClient(app, base_url="https://testserver") as prod:
        page = prod.get("/login")

        assert page.status_code == 200
        assert prod.cookies.get("c4c_session") in (None, "")


def test_auto_sign_in_with_an_empty_database_falls_back_to_the_sign_in_page(
    settings, tmp_path
):
    app = _demo_app(settings, tmp_path, accounts=False, demo_auto_sign_in=True)
    with TestClient(app, base_url="https://testserver") as prod:
        page = prod.get("/scan", follow_redirects=False)

        assert page.status_code == 303
        assert page.headers["location"].startswith("/login")


def test_the_flags_are_read_from_the_environment(settings, monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("DEMO_SIGN_IN", "1")
    monkeypatch.setenv("DEMO_AUTO_SIGN_IN", "yes")

    loaded = Settings.from_env()

    assert loaded.dev_sign_in is True
    assert loaded.demo_auto_sign_in is True

    monkeypatch.setenv("DEMO_SIGN_IN", "")
    monkeypatch.setenv("DEMO_AUTO_SIGN_IN", "")
    plain = dataclasses.replace(Settings.from_env(), environment="production")
    assert plain.dev_sign_in is False
    assert plain.demo_auto_sign_in is False
