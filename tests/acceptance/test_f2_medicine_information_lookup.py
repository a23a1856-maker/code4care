"""Acceptance tests: Medicine Information Lookup (use case UC2 in docs/REQUIREMENTS.md)

Real tests for AC2.1, AC2.2 and AC2.3, replacing the GigaLab placeholders.
"""
from __future__ import annotations

import pytest

from tests.conftest import sign_in
from tests.helpers import count, csrf_token


def test_ac2_1(client, world):
    """Given a signed-in Registered user, when they search the medicine database
    using the scanned barcode, then the result is saved for their business only."""
    tenant_a = world["tenants"]["a"]
    tenant_b = world["tenants"]["b"]
    medicine = world["medicines"]["a"][3]
    barcode = medicine["barcode"]

    signed = sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get("/search")
    assert page.status_code == 200
    token = csrf_token(page.text)

    response = client.post(
        "/lookup/barcode",
        data={"barcode": barcode, "request_id": "lookup-0001", "csrf_token": token},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200, response.text
    assert medicine["name"] in response.text
    assert 'data-lookup="found"' in response.text

    assert count(world["conn"], "scans", tenant_a) == 1
    assert count(world["conn"], "scans", tenant_b) == 0
    row = world["conn"].execute(
        "SELECT tenant_id, user_id, barcode, source FROM scans"
    ).fetchone()
    assert row["tenant_id"] == tenant_a
    assert row["user_id"] == world["users"]["owner_a"]["id"]
    assert row["barcode"] == barcode
    assert row["source"] == "search"


def test_ac2_1_catalogue_is_per_business(client, world):
    """Business B's catalogue is not searched for business A."""
    tenant_b = world["tenants"]["b"]
    b_only = [
        row
        for row in world["medicines"]["b"]
        if row["barcode"] not in {m["barcode"] for m in world["medicines"]["a"]}
    ]
    shared = world["medicines"]["a"][0]["barcode"]
    unique_b = b_only[0]["barcode"]

    sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get("/search")
    token = csrf_token(page.text)

    own = client.post(
        "/lookup/barcode",
        data={"barcode": shared, "csrf_token": token},
        headers={"HX-Request": "true"},
    )
    assert own.status_code == 200
    assert 'data-lookup="found"' in own.text

    other = client.post(
        "/lookup/barcode",
        data={"barcode": unique_b, "csrf_token": token},
        headers={"HX-Request": "true"},
    )
    assert other.status_code == 200
    assert 'data-lookup="not_found"' in other.text
    assert count(world["conn"], "scans", tenant_b) == 0


@pytest.mark.parametrize("role", ["pharmacist_a", "guest_a", "admin_a"])
def test_ac2_2(client, world, role):
    """Given a user without permission, when they try a lookup, then it is refused."""
    signed = sign_in(client, world["users"][role]["email"])
    page = client.get("/search", follow_redirects=False)
    assert page.status_code == 403
    assert 'data-error="forbidden"' in page.text

    posted = client.post(
        "/lookup/barcode",
        data={"barcode": world["medicines"]["a"][0]["barcode"], "csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )
    assert posted.status_code == 403
    assert count(world["conn"], "scans", world["tenants"]["a"]) == 0


def test_ac2_2_signed_out(client, world):
    page = client.get("/search", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"].startswith("/login")

    posted = client.post("/lookup/barcode", data={"barcode": "5000000000000"})
    assert posted.status_code == 401
    assert count(world["conn"], "scans") == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"barcode": ""},
        {"barcode": "   "},
        {"barcode": "not-a-barcode"},
        {"barcode": "5000000000001"},  # bad EAN-13 check digit
        {"query": "x" * 200},
        {},
    ],
)
def test_ac2_3(client, world, payload):
    """Given invalid input, when it is submitted, then a clear message shows and
    nothing is saved."""
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    data = {**payload, "csrf_token": signed.csrf}
    response = client.post("/lookup/barcode", data=data, headers={"HX-Request": "true"})

    assert response.status_code == 422, response.text
    assert 'data-error="invalid_lookup"' in response.text
    assert "Masukkan kod bar" in response.text or "Kod bar tidak sah" in response.text
    assert count(world["conn"], "scans", world["tenants"]["a"]) == 0


def test_ac2_3_search_page_rejects_blank_query(client, world):
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    response = client.post(
        "/search",
        data={"q": "  ", "csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 422
    assert 'data-error="invalid_lookup"' in response.text
    assert count(world["conn"], "scans") == 0
