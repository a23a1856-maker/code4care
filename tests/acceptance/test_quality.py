"""Quality targets (docs/QUALITY.md) for milestone M6: real tests and scripted checks."""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import sign_in
from tests.helpers import FakeEmailer, count, csrf_token

ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------- security


def test_security_validate(client, world):
    """Every input is validated on the server, and reflected safely."""
    page = client.get("/login")
    bad_email = client.post(
        "/login",
        data={"email": "<script>alert(1)</script>", "csrf_token": csrf_token(page.text)},
    )
    assert bad_email.status_code == 422
    assert "<script>alert(1)" not in bad_email.text

    signed = sign_in(client, world["users"]["owner_a"]["email"])
    barcode = world["medicines"]["a"][0]["barcode"]

    oversize = client.post(
        "/scan/lookup",
        data={"barcode": "9" * 5000, "csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )
    assert oversize.status_code == 422

    bad_role = client.post(
        f"/team/{world['users']['pharmacist_a']['id']}/role",
        data={"role": "root", "csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )
    assert bad_role.status_code == 422

    bad_medicine = client.get("/medicines/not-a-number")
    assert bad_medicine.status_code == 404

    # A search term that looks like markup comes back escaped, never executed.
    escaped = client.post(
        "/search",
        data={"q": "<script>alert('x')</script>", "csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )
    assert escaped.status_code == 200
    assert "<script>alert('x')</script>" not in escaped.text

    # The valid barcode still works, proving the checks do not block good input.
    good = client.post(
        "/scan/lookup",
        data={"barcode": barcode, "csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )
    assert good.status_code == 200


def test_security_secrets(client, world, caplog):
    """Secrets live only in environment variables, never in code or pages."""
    forbidden = ("sk_live_", "sk_test_", "AKIA", "BEGIN RSA PRIVATE KEY", "password=")
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"{marker} in {path}"

    assert ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert not (ROOT / ".env").exists() or ".env" in (
        ROOT / ".gitignore"
    ).read_text(encoding="utf-8")

    settings = client.app.state.settings
    assert "unit-test-secret" not in repr(settings)

    caplog.set_level("DEBUG")
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    pages = [client.get(path) for path in ("/", "/scan", "/settings")]
    for page in pages:
        assert settings.app_secret not in page.text
        assert settings.google_client_secret not in page.text
        assert "google-secret" not in page.text
        if signed.token:
            assert signed.token not in page.text
    assert settings.app_secret not in caplog.text
    assert world["users"]["owner_a"]["email"] not in caplog.text


def test_security_https(settings, world, tmp_path):
    """HTTPS only, secure cookies and CSRF protection in production."""
    import dataclasses

    from app.main import create_app

    production = dataclasses.replace(
        settings,
        environment="production",
        base_url="https://code4care.example",
        database_path=str(tmp_path / "prod.db"),
    )
    app = create_app(production)
    app.state.emailer = FakeEmailer()
    from app import db as db_module

    prod_conn = db_module.connect(production.database_path)
    prod_tenant = db_module.create_tenant(prod_conn, "Farmasi HTTPS")
    db_module.create_user(
        prod_conn, prod_tenant, world["users"]["member_a"]["email"],
        "Registered user", verified=True,
    )
    prod_conn.close()

    with TestClient(app, base_url="https://testserver") as prod_client:
        plain = prod_client.get(
            "/health", headers={"x-forwarded-proto": "http"}, follow_redirects=False
        )
        assert plain.status_code == 308
        assert plain.headers["location"].startswith("https://")

        secure = prod_client.get("/health", headers={"x-forwarded-proto": "https"})
        assert secure.status_code == 200
        assert "max-age=31536000" in secure.headers["strict-transport-security"]
        assert "default-src 'self'" in secure.headers["content-security-policy"]
        assert secure.headers["x-frame-options"] == "DENY"
        assert secure.headers["x-content-type-options"] == "nosniff"

        form = prod_client.get("/login", headers={"x-forwarded-proto": "https"})
        token = csrf_token(form.text)

        # Without the CSRF token the sign-in form is refused.
        no_token = prod_client.post(
            "/login", data={"email": "someone@farmasi.example"},
            headers={"x-forwarded-proto": "https"}, follow_redirects=False,
        )
        assert no_token.status_code == 403
        assert 'data-error="csrf"' in no_token.text

        sent = prod_client.post(
            "/login",
            data={"email": world["users"]["member_a"]["email"], "csrf_token": token},
            headers={"x-forwarded-proto": "https"},
        )
        assert sent.status_code == 200

    from tests.helpers import latest_message, magic_path

    link = magic_path(latest_message(app.state.emailer, world["users"]["member_a"]["email"]))
    signed_in = prod_client.get(
        link, headers={"x-forwarded-proto": "https"}, follow_redirects=False
    )
    assert signed_in.status_code == 303
    set_cookie = signed_in.headers.get("set-cookie", "")
    assert "c4c_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "samesite=lax" in set_cookie.lower()


def test_security_ratelimit(client):
    """Rate limits guard sign-in and every public route."""
    from app.main import DEFAULT_PUBLIC_LIMIT, PUBLIC_RATE_LIMITS

    assert DEFAULT_PUBLIC_LIMIT[0] <= 120
    assert PUBLIC_RATE_LIMITS[("POST", "/login")][0] <= 20

    page = client.get("/login")
    token = csrf_token(page.text)
    statuses = [
        client.post("/login", data={"email": "a@farmasi.example", "csrf_token": token}).status_code
        for _ in range(25)
    ]
    assert 429 in statuses, statuses
    limited = client.post(
        "/login", data={"email": "a@farmasi.example", "csrf_token": token}
    )
    assert "Terlalu banyak" in limited.text
    assert limited.headers.get("retry-after")

    # The counters are in SQLite, so a restart does not reset them.
    rows = client.app.state.settings.database_path
    conn = sqlite3.connect(rows)
    try:
        assert conn.execute("SELECT COUNT(*) FROM rate_limits").fetchone()[0] > 0
    finally:
        conn.close()


def test_security_deps():
    """A dependency audit runs on every build (pip-audit)."""
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pip-audit" in workflow
    assert "pytest" in workflow
    assert "requirements.txt" in workflow

    audit_script = (ROOT / "scripts" / "audit.sh").read_text(encoding="utf-8")
    assert "pip-audit" in audit_script

    if shutil.which("pip-audit"):
        result = subprocess.run(
            [shutil.which("pip-audit"), "-r", "requirements.txt"],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )
        assert result.returncode == 0, (result.stdout + result.stderr)[-3000:]


def test_security_owasp():
    """Reviewed against the OWASP Top 10 before launch."""
    review = (ROOT / "docs" / "SECURITY_REVIEW.md").read_text(encoding="utf-8")
    for number in range(1, 11):
        assert f"A{number:02d}" in review, f"A{number:02d} missing from the review"
    assert review.lower().count("status:") >= 10
    for control in ("CSRF", "rate limit", "tenant", "CSP", "validat"):
        assert control.lower() in review.lower(), control
    assert "CODE4CARE" in review


# ----------------------------------------------------------------- reliability


def test_reliability_errors(client, world, monkeypatch):
    """Every error gives a clear message, and nothing is left half-saved."""
    # A failed outbound email: clear message, no unusable sign-in code stored.
    class BrokenEmail(FakeEmailer):
        def send(self, to, subject, text):
            from app.outbound import OutboundError

            raise OutboundError("email provider is down")

    client.app.state.emailer = BrokenEmail()
    page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "email": world["users"]["member_a"]["email"],
            "csrf_token": csrf_token(page.text),
        },
    )
    assert response.status_code == 503
    assert "Sila cuba sebentar lagi" in response.text
    rows = world["conn"].execute(
        "SELECT COUNT(*) FROM login_codes WHERE tenant_id = ?",
        (world["tenants"]["a"],),
    ).fetchone()[0]
    assert rows == 0

    # A failure while handling a scan: clear message, no partial scan saved.
    from app import main as main_module

    client.app.state.emailer = FakeEmailer()

    def boom(*args, **kwargs):
        raise RuntimeError("database is unavailable")

    monkeypatch.setattr(main_module.db, "save_scan", boom)
    app = client.app
    with TestClient(app, raise_server_exceptions=False) as second:
        signed = sign_in(second, world["users"]["owner_a"]["email"])
        failed = second.post(
            "/scan/lookup",
            data={
                "barcode": world["medicines"]["a"][0]["barcode"],
                "csrf_token": signed.csrf,
            },
            headers={"HX-Request": "true"},
        )
        assert failed.status_code == 500
        assert 'data-error="server_error"' in failed.text
        assert "Tiada data disimpan" in failed.text
    assert count(world["conn"], "scans", world["tenants"]["a"]) == 0

    # Every refusal says what to do next.
    signed = sign_in(client, world["users"]["pharmacist_a"]["email"])
    forbidden = client.get("/team")
    assert 'data-error="forbidden"' in forbidden.text
    assert "Hubungi pemilik perniagaan" in forbidden.text


def test_reliability_timeouts():
    """Calls to outside services time out and retry with back-off."""
    import httpx

    from app.outbound import OutboundError, request_with_retry

    calls = []
    sleeps = []

    class FlakyClient:
        def __init__(self, failures):
            self.failures = failures
            self.seen = 0

        def request(self, method, url, **kwargs):
            self.seen += 1
            calls.append(kwargs)
            if self.seen <= self.failures:
                raise httpx.ConnectTimeout("upstream timed out")
            return httpx.Response(200, json={"ok": True}, request=httpx.Request(method, url))

    response = request_with_retry(
        "GET",
        "https://example.test/api",
        client=FlakyClient(2),
        retries=2,
        timeout=3.0,
        sleep=sleeps.append,
    )
    assert response.json() == {"ok": True}
    assert len(calls) == 3
    assert sleeps == [0.25, 0.5]  # exponential back-off
    assert all(call["timeout"] == 3.0 for call in calls)

    with pytest.raises(OutboundError):
        request_with_retry(
            "GET",
            "https://example.test/api",
            client=FlakyClient(10),
            retries=1,
            sleep=lambda seconds: None,
        )

    from app.emailer import HttpEmailer

    class NoKey:
        email_api_key = ""

    with pytest.raises(OutboundError):
        HttpEmailer(NoKey()).send("a@b.my", "subject", "text")


def test_reliability_backups(world, tmp_path):
    """A backup is taken and restored once, to prove it works."""
    from scripts.backup import backup_database
    from scripts.restore import restore_database

    source_path = world["conn"].execute("PRAGMA database_list").fetchone()[2]
    source = Path(source_path)
    destination = tmp_path / "backup.db"

    backup_database(source, destination)
    assert destination.exists() and destination.stat().st_size > 0

    conn = world["conn"]
    conn.execute(
        "INSERT INTO scans (tenant_id, user_id, barcode, source, found, created_at) "
        "VALUES (?, ?, ?, 'camera', 0, ?)",
        (world["tenants"]["a"], world["users"]["owner_a"]["id"], "5000000000000", "2026-10-22T00:00:00+00:00"),
    )
    conn.commit()
    before = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]

    restore_database(destination, source)
    conn.close()

    restored = sqlite3.connect(str(source))
    restored.row_factory = sqlite3.Row
    try:
        after = restored.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
        assert after == before - 1
        assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        restored.close()


def test_reliability_idempotent(client, world):
    """A retry never saves the same action twice."""
    from app import db

    signed = sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get("/scan")
    token = csrf_token(page.text)
    barcode = world["medicines"]["a"][0]["barcode"]

    for _ in range(3):
        response = client.post(
            "/scan/lookup",
            data={"barcode": barcode, "request_id": "retry-key-1", "csrf_token": token},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
    assert count(world["conn"], "scans", world["tenants"]["a"]) == 1

    again = client.post(
        "/scan/lookup",
        data={"barcode": barcode, "request_id": "another-key", "csrf_token": token},
        headers={"HX-Request": "true"},
    )
    assert again.status_code == 200
    assert count(world["conn"], "scans", world["tenants"]["a"]) == 2

    assert db.remember_idempotent(world["conn"], world["tenants"]["a"], "pay-1", "billing") is True
    assert db.remember_idempotent(world["conn"], world["tenants"]["a"], "pay-1", "billing") is False


# ----------------------------------------------------------------- performance


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    index = max(0, int(len(ordered) * 0.95) - 1)
    return ordered[index]


def test_performance_page(client, world):
    """p95 page render under 2 seconds, with a page weight a phone can load on 4G."""
    sign_in(client, world["users"]["owner_a"]["email"])
    for path in ("/", "/scan", "/search", "/history", "/team"):
        timings, sizes = [], []
        for _ in range(20):
            started = time.perf_counter()
            response = client.get(path)
            timings.append((time.perf_counter() - started) * 1000)
            sizes.append(len(response.content))
            assert response.status_code == 200, path
        assert _p95(timings) < 2000, (path, _p95(timings))
        assert max(sizes) < 250_000, (path, max(sizes))


def test_performance_api(client, world):
    """p95 API response under 500 ms."""
    health = []
    for _ in range(50):
        started = time.perf_counter()
        assert client.get("/health").status_code == 200
        health.append((time.perf_counter() - started) * 1000)
    assert _p95(health) < 500

    signed = sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get("/scan")
    token = csrf_token(page.text)
    barcode = world["medicines"]["a"][0]["barcode"]
    lookups = []
    for index in range(30):
        started = time.perf_counter()
        response = client.post(
            "/scan/lookup",
            data={"barcode": barcode, "request_id": f"perf-{index}", "csrf_token": token},
            headers={"HX-Request": "true"},
        )
        lookups.append((time.perf_counter() - started) * 1000)
        assert response.status_code == 200
    assert _p95(lookups) < 500


def test_performance_indexes(world):
    """A database index for every list and search."""
    conn = world["conn"]
    sql = " ".join(
        row["sql"] or ""
        for row in conn.execute("SELECT sql FROM sqlite_master WHERE type = 'index'")
    )
    for index in (
        "idx_medicines_tenant_barcode",
        "idx_medicines_tenant_name",
        "idx_medicines_tenant_ingredient",
        "idx_scans_tenant_created",
        "idx_scans_tenant_user",
        "idx_audit_log_tenant_created",
        "idx_users_tenant_email",
        "idx_favourites_tenant_user",
    ):
        assert index in sql, index

    plan = lambda query, params: " ".join(
        row["detail"] for row in conn.execute("EXPLAIN QUERY PLAN " + query, params)
    )

    barcode_plan = plan(
        "SELECT * FROM medicines WHERE tenant_id = ? AND barcode = ?",
        (world["tenants"]["a"], world["medicines"]["a"][0]["barcode"]),
    )
    assert "USING INDEX" in barcode_plan, barcode_plan

    scans_plan = plan(
        "SELECT * FROM scans WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 50",
        (world["tenants"]["a"],),
    )
    assert "USING INDEX" in scans_plan, scans_plan

    users_plan = plan(
        "SELECT * FROM users WHERE tenant_id = ? AND email_normalized = ?",
        (world["tenants"]["a"], world["users"]["owner_a"]["email"]),
    )
    assert "USING INDEX" in users_plan, users_plan
