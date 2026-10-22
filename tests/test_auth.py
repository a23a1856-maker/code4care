"""Authentication: magic link, Google, verification, lockout and two-factor."""
from __future__ import annotations

import logging
import re

import pytest

from tests.conftest import sign_in
from tests.helpers import latest_message, magic_path, six_digit_code, csrf_token


class FakeGoogle:
    """Stands in for Google's OAuth endpoints (the provider's test mode)."""

    def __init__(self):
        self.profile = {"email": "", "email_verified": True, "sub": "google-sub-1"}

    def authorize_url(self, state: str) -> str:
        return f"https://accounts.google.test/o/oauth2/v2/auth?state={state}"

    def exchange_code(self, code: str) -> dict:
        assert code, "the callback must exchange the code"
        return dict(self.profile)


@pytest.fixture
def google(app):
    fake = FakeGoogle()
    app.state.google = fake
    return fake


def test_signed_out_request_to_a_private_page_is_refused(client):
    for path in ("/scan", "/search", "/team", "/billing", "/settings", "/usage"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"].startswith("/login"), path

    assert client.post("/scan/lookup", data={"barcode": "5000000000000"}).status_code == 401


def test_magic_link_sign_in_and_sign_out(client, world):
    email = world["users"]["member_a"]["email"]
    signed = sign_in(client, email)

    page = client.get("/")
    assert page.status_code == 200
    assert email in page.text

    signed_out = client.post(
        "/logout", data={"csrf_token": csrf_token(page.text)}, follow_redirects=False
    )
    assert signed_out.status_code == 303
    assert client.cookies.get("c4c_session") in (None, "")

    # The session row is gone on the server, not only in the browser.
    remaining = world["conn"].execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert remaining == 0

    # Replaying the old cookie must not work.
    client.cookies.set("c4c_session", signed.token)
    assert client.get("/scan", follow_redirects=False).status_code == 303


def test_no_password_is_stored_and_no_token_in_logs(client, world, caplog):
    columns = [
        row["name"]
        for row in world["conn"].execute("PRAGMA table_info(users)").fetchall()
    ]
    assert "password" not in columns
    assert "password_hash" not in columns

    caplog.set_level(logging.DEBUG)
    signed = sign_in(client, world["users"]["member_a"]["email"])
    client.get("/")

    row = world["conn"].execute(
        "SELECT token_hash FROM sessions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["token_hash"] != signed.token
    assert re.fullmatch(r"[0-9a-f]{64}", row["token_hash"])
    assert signed.token not in caplog.text
    assert "unit-test-secret" not in caplog.text


def test_sign_in_with_google(client, world, google):
    email = world["users"]["member_a"]["email"]
    google.profile = {"email": email, "email_verified": True, "sub": "google-sub-42"}

    start = client.get("/auth/google", follow_redirects=False)
    assert start.status_code == 303
    assert start.headers["location"].startswith("https://accounts.google.test/")
    state = re.search(r"state=([A-Za-z0-9_\-]+)", start.headers["location"]).group(1)

    callback = client.get(
        f"/auth/google/callback?code=test-code&state={state}", follow_redirects=False
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "/"
    assert client.cookies.get("c4c_session")

    page = client.get("/")
    assert email in page.text


def test_google_refuses_an_unverified_email(client, world, google):
    google.profile = {
        "email": world["users"]["member_a"]["email"],
        "email_verified": False,
        "sub": "google-sub-43",
    }

    start = client.get("/auth/google", follow_redirects=False)
    state = re.search(r"state=([A-Za-z0-9_\-]+)", start.headers["location"]).group(1)
    callback = client.get(
        f"/auth/google/callback?code=test-code&state={state}", follow_redirects=False
    )

    assert callback.status_code == 403
    assert 'data-error="email_unverified"' in callback.text
    assert client.cookies.get("c4c_session") in (None, "")
    assert world["conn"].execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_an_unverified_account_cannot_use_the_app(client, world):
    """A session that exists for an unverified email is refused on every page."""
    from app import auth

    conn = world["conn"]
    user = world["users"]["unverified_a"]
    token, _ = auth.create_session(
        conn, tenant_id=user["tenant_id"], user_id=user["id"], settings=client.app.state.settings
    )
    conn.commit()

    client.cookies.set("c4c_session", token)
    response = client.get("/scan", follow_redirects=False)
    assert response.status_code == 403
    assert 'data-error="email_unverified"' in response.text
    assert client.get("/", follow_redirects=False).status_code == 200  # public landing only


def test_unknown_email_gets_the_same_answer(client):
    page = client.get("/login")
    response = client.post(
        "/login",
        data={"email": "nobody@example.com", "csrf_token": csrf_token(page.text)},
    )
    assert response.status_code == 200
    assert "Jika alamat ini berdaftar" in response.text
    assert client.app.state.emailer.messages == []


def test_repeated_failed_sign_ins_are_slowed_then_locked(client, world):
    email = world["users"]["owner_a"]["email"]
    page = client.get("/login")
    client.post("/login", data={"email": email, "csrf_token": csrf_token(page.text)})
    path = magic_path(latest_message(client.app.state.emailer, email))
    assert client.get(path, follow_redirects=False).status_code == 303  # now at 2FA

    form = client.get("/login/2fa")
    token = csrf_token(form.text)
    statuses = []
    for _ in range(6):
        response = client.post(
            "/login/2fa", data={"code": "000000", "csrf_token": token}, follow_redirects=False
        )
        statuses.append(response.status_code)

    assert 429 in statuses, statuses
    # After enough failures the account is locked: even the right code is refused.
    right = six_digit_code(latest_message(client.app.state.emailer, email))
    locked = client.post(
        "/login/2fa", data={"code": right, "csrf_token": token}, follow_redirects=False
    )
    assert locked.status_code == 429
    assert "dikunci" in locked.text.lower()
    assert client.cookies.get("c4c_session") in (None, "")


def test_owner_must_pass_two_factor(client, world):
    email = world["users"]["owner_a"]["email"]
    page = client.get("/login")
    client.post("/login", data={"email": email, "csrf_token": csrf_token(page.text)})
    path = magic_path(latest_message(client.app.state.emailer, email))

    first = client.get(path, follow_redirects=False)
    assert first.status_code == 303
    assert first.headers["location"].startswith("/login/2fa")
    assert client.cookies.get("c4c_session") in (None, "")
    assert world["conn"].execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0

    form = client.get("/login/2fa")
    code = six_digit_code(latest_message(client.app.state.emailer, email))
    done = client.post(
        "/login/2fa",
        data={"code": code, "csrf_token": csrf_token(form.text)},
        follow_redirects=False,
    )
    assert done.status_code == 303
    assert client.cookies.get("c4c_session")
    assert "csrf=" not in client.cookies.get("c4c_session")


def test_session_cookie_flags(settings, world):
    from app import auth

    assert auth.cookie_flags(settings)["httponly"] is True
    assert auth.cookie_flags(settings)["samesite"] == "lax"
    assert auth.cookie_flags(settings)["secure"] is False  # local http in testing

    from app.config import Settings

    production = Settings.from_env()
    object.__setattr__(production, "environment", "production")
    assert auth.cookie_flags(production)["secure"] is True
