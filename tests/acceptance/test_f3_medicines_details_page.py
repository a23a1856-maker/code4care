"""Acceptance tests: Medicines details page (use case UC3 in docs/REQUIREMENTS.md)

Real tests for AC3.1, AC3.2 and AC3.3, replacing the GigaLab placeholders.
"""
from __future__ import annotations

import pytest

from tests.conftest import sign_in
from tests.helpers import count, csrf_token


def test_ac3_1(client, world):
    """Given a signed-in Registered user, when they display a medicine, then the
    verified details show and the view is saved for their business only."""
    tenant_a = world["tenants"]["a"]
    tenant_b = world["tenants"]["b"]
    medicine = world["medicines"]["a"][0]

    sign_in(client, world["users"]["owner_a"]["email"])
    response = client.get(f"/medicines/{medicine['id']}")

    assert response.status_code == 200, response.text
    assert 'data-page="medicine"' in response.text
    for field in (
        medicine["name"],
        medicine["brand"],
        medicine["active_ingredient"],
        medicine["strength"],
        medicine["dosage_form"],
        medicine["manufacturer"],
    ):
        assert field in response.text

    views = world["conn"].execute(
        "SELECT tenant_id, user_id, medicine_id FROM medicine_views"
    ).fetchall()
    assert len(views) == 1
    assert views[0]["tenant_id"] == tenant_a
    assert views[0]["user_id"] == world["users"]["owner_a"]["id"]
    assert views[0]["medicine_id"] == medicine["id"]

    # Tenant B cannot open tenant A's medicine, and nothing is written for B.
    sign_in(client, world["users"]["owner_b"]["email"])
    blocked = client.get(f"/medicines/{medicine['id']}")
    assert blocked.status_code == 404
    assert 'data-error="medicine_not_found"' in blocked.text
    assert count(world["conn"], "medicine_views", tenant_b) == 0


def test_ac3_1_only_verified_information_is_shown(client, world):
    """Unverified rows are named as such, without unverified medical claims."""
    unverified_id = world["conn"].execute(
        "SELECT id FROM medicines WHERE tenant_id = ? AND verified = 0 LIMIT 1",
        (world["tenants"]["a"],),
    ).fetchone()["id"]

    sign_in(client, world["users"]["owner_a"]["email"])
    response = client.get(f"/medicines/{unverified_id}")

    assert response.status_code == 200
    assert 'data-verified="false"' in response.text
    assert "belum disahkan" in response.text


@pytest.mark.parametrize("role", ["pharmacist_a", "guest_a", "admin_a"])
def test_ac3_2(client, world, role):
    """Given a user without permission, when they open a medicine, then it is refused."""
    medicine = world["medicines"]["a"][0]
    signed = sign_in(client, world["users"][role]["email"])

    response = client.get(f"/medicines/{medicine['id']}", follow_redirects=False)
    assert response.status_code == 403
    assert 'data-error="forbidden"' in response.text
    assert count(world["conn"], "medicine_views", world["tenants"]["a"]) == 0
    assert signed.email.endswith("farmasi.example")


def test_ac3_2_signed_out(client, world):
    medicine = world["medicines"]["a"][0]
    response = client.get(f"/medicines/{medicine['id']}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")
    assert count(world["conn"], "medicine_views") == 0


@pytest.mark.parametrize("bad_id", ["abc", "0", "-1", "999999", "1e9", "%00"])
def test_ac3_3(client, world, bad_id):
    """Given invalid input, when it is submitted, then a clear message shows and
    nothing is saved."""
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    response = client.get(f"/medicines/{bad_id}")

    assert response.status_code == 404, response.text
    assert 'data-error="medicine_not_found"' in response.text
    assert "Ubat tidak dijumpai" in response.text
    assert count(world["conn"], "medicine_views") == 0
    _ = signed
