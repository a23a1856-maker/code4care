"""Acceptance tests: barcode scanner (use case UC1 in docs/REQUIREMENTS.md)

Real tests for AC1.1, AC1.2 and AC1.3, replacing the GigaLab placeholders.
The camera decodes the barcode in the browser and posts the digits to the
server; these tests exercise that server side end to end.
"""
from __future__ import annotations

import pytest

from tests.conftest import sign_in
from tests.helpers import count, csrf_token


def test_ac1_1(client, world):
    """Given a signed-in Registered user, when they scan a medicine barcode,
    then the result is saved for their business only."""
    tenant_a = world["tenants"]["a"]
    tenant_b = world["tenants"]["b"]
    barcode = world["medicines"]["a"][0]["barcode"]
    medicine_name = world["medicines"]["a"][0]["name"]

    signed = sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get("/scan")
    assert page.status_code == 200
    token = csrf_token(page.text)

    response = client.post(
        "/scan/lookup",
        data={"barcode": barcode, "request_id": "scan-0001", "csrf_token": token},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200, response.text
    assert medicine_name in response.text
    assert 'data-scan="saved"' in response.text

    # Saved against this business, and only this business.
    assert count(world["conn"], "scans", tenant_a) == 1
    assert count(world["conn"], "scans", tenant_b) == 0
    saved = world["conn"].execute(
        "SELECT tenant_id, user_id, barcode, source, found FROM scans"
    ).fetchone()
    assert saved["tenant_id"] == tenant_a
    assert saved["user_id"] == world["users"]["owner_a"]["id"]
    assert saved["barcode"] == barcode
    assert saved["found"] == 1
    assert saved["source"] == "camera"

    # A manager of the other pharmacy cannot see it.
    sign_in(client, world["users"]["owner_b"]["email"])
    history = client.get("/history")
    assert history.status_code == 200
    assert barcode not in history.text
    client.post("/logout", data={"csrf_token": csrf_token(history.text)})
    assert signed.email == world["users"]["owner_a"]["email"]


@pytest.mark.parametrize(
    "role",
    [
        "pharmacist_a",
        "guest_a",
        "admin_a",
    ],
)
def test_ac1_2(client, world, role):
    """Given a user without permission, when they try to scan, then it is refused."""
    signed = sign_in(client, world["users"][role]["email"])

    page = client.get("/scan", follow_redirects=False)
    assert page.status_code == 403
    assert 'data-error="forbidden"' in page.text

    posted = client.post(
        "/scan/lookup",
        data={"barcode": world["medicines"]["a"][0]["barcode"], "csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )
    assert posted.status_code == 403
    assert count(world["conn"], "scans", world["tenants"]["a"]) == 0


def test_ac1_2_signed_out(client, world):
    """Given nobody is signed in, when they try to scan, then it is refused."""
    page = client.get("/scan", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"].startswith("/login")

    posted = client.post(
        "/scan/lookup",
        data={"barcode": world["medicines"]["a"][0]["barcode"]},
    )
    assert posted.status_code == 401
    assert count(world["conn"], "scans", world["tenants"]["a"]) == 0


@pytest.mark.parametrize(
    "bad_barcode",
    [
        "",
        "abc",
        "12345",
        "4006381333932",  # EAN-13 with a bad check digit
        "'; DROP TABLE scans; --",
        "12345678901234567890",
    ],
)
def test_ac1_3(client, world, bad_barcode):
    """Given invalid input, when it is submitted, then a clear message shows and
    nothing is saved."""
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    response = client.post(
        "/scan/lookup",
        data={"barcode": bad_barcode, "csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 422, response.text
    assert 'data-error="invalid_barcode"' in response.text
    assert "Kod bar tidak sah" in response.text
    assert count(world["conn"], "scans", world["tenants"]["a"]) == 0
    # The table is still there: the input never reaches SQL.
    assert count(world["conn"], "scans") == 0
