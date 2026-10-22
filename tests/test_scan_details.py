"""A QR scan must answer the four questions a customer asks at the counter:
what is it, what is it for, what is the dose, and how much do I take?

The QR label encodes the product code; the browser decodes it and posts it to
/scan/lookup exactly like a barcode. These tests go through that same route.
"""
from __future__ import annotations

import json

from app import db, labels
from app.seed_data import ean13
from tests.conftest import sign_in
from tests.helpers import csrf_token

CARD = "Ujian Dos 250 mg"
UNVERIFIED = "Ujian Belum Sah 500 mg"


def _scan(client, code: str):
    page = client.get("/scan")
    return client.post(
        "/scan/lookup",
        data={"barcode": code, "csrf_token": csrf_token(page.text)},
        headers={"HX-Request": "true"},
    )


def _add_catalogue_row(world, *, barcode: str, name: str, verified: bool, extra: dict) -> dict:
    """Add one imported-style row to pharmacy A and return it."""
    conn = world["conn"]
    tenant = world["tenants"]["a"]
    db.upsert_imported_medicine(
        conn,
        tenant,
        {
            "barcode": barcode,
            "name": name,
            "brand": "Ujian",
            "active_ingredient": "Bahan ujian",
            "strength": "250 mg",
            "dosage_form": "Tablet",
            "manufacturer": "Ujian Sdn Bhd",
            "uses": "Mengurangkan sakit ringan.",
            "dosage_instructions": "Dewasa: 1 tablet setiap 6 jam.",
            "warnings": "Jangan melebihi 4 tablet sehari.",
            "side_effects": "",
            "storage": "",
            "category": "Sakit",
            "extra_json": json.dumps(extra),
        },
        verified=verified,
        source="Katalog ujian",
    )
    conn.commit()
    row = db.find_medicine_by_barcode(conn, tenant, barcode)
    assert row is not None
    return row


def test_scan_result_shows_name_use_dose_and_how_much(client, world):
    """AC2/AC3 through the scanner: the result card carries the four answers."""
    medicine = next(
        m for m in world["medicines"]["a"]
        if m["verified"] and m["uses"] and m["dosage_instructions"]
    )
    sign_in(client, world["users"]["owner_a"]["email"])

    response = _scan(client, medicine["barcode"])

    assert response.status_code == 200
    body = response.text
    assert medicine["name"] in body
    assert '<p class="eyebrow">Kegunaan</p>' in body
    assert medicine["uses"] in body
    assert '<p class="eyebrow">Dos</p>' in body
    assert medicine["dosage_instructions"] in body
    assert medicine["strength"] in body and medicine["dosage_form"] in body
    if medicine["warnings"]:
        assert '<p class="eyebrow">Amaran</p>' in body
        assert medicine["warnings"] in body
    assert f'/medicines/{medicine["id"]}' in body


def test_qr_payload_scan_shows_the_same_details(client, world):
    """The QR payload is the code the browser posts; it must resolve to details."""
    medicine = next(
        m for m in world["medicines"]["a"]
        if m["verified"] and m["uses"] and m["dosage_instructions"]
    )
    payload = labels.label_item(medicine)["code"]
    assert payload == medicine["barcode"]

    sign_in(client, world["users"]["owner_a"]["email"])
    body = _scan(client, payload).text

    assert medicine["name"] in body
    assert medicine["dosage_instructions"] in body


def test_scan_result_shows_how_to_take_from_the_imported_catalogue(client, world):
    """Imported rows carry 'how to take' and the pack size; both belong on the card."""
    extra = {
        "how_to_take": "Telan dengan segelas air selepas makan.",
        "reg_class": "OTC",
        "pack_size": "1 kotak = 10 tablet",
    }
    medicine = _add_catalogue_row(
        world, barcode=ean13("955123450001"), name=CARD, verified=True, extra=extra
    )
    sign_in(client, world["users"]["owner_a"]["email"])

    body = _scan(client, medicine["barcode"]).text

    assert CARD in body
    assert '<p class="eyebrow">Cara pengambilan</p>' in body
    assert extra["how_to_take"] in body
    assert extra["pack_size"] in body
    assert "Maklumat disahkan" in body


def test_scan_result_hides_details_until_a_pharmacist_verifies(client, world):
    """Unverified rows must not show uses or dose — the same rule as the detail page."""
    medicine = _add_catalogue_row(
        world,
        barcode=ean13("955123450002"),
        name=UNVERIFIED,
        verified=False,
        extra={"how_to_take": "Telan dengan air."},
    )
    sign_in(client, world["users"]["owner_a"]["email"])

    body = _scan(client, medicine["barcode"]).text

    assert UNVERIFIED in body
    assert "belum disahkan" in body
    assert '<p class="eyebrow">Dos</p>' not in body
    assert '<p class="eyebrow">Kegunaan</p>' not in body
    assert "Dewasa: 1 tablet setiap 6 jam." not in body
    assert "Telan dengan air." not in body


def test_scan_of_an_unknown_qr_code_is_refused_clearly(client, world):
    """A QR that is not in this business's catalogue must say so, not 500."""
    sign_in(client, world["users"]["owner_a"]["email"])

    response = _scan(client, "C4C-9999")

    assert response.status_code == 422
    assert 'data-error="invalid_barcode"' in response.text


def test_owner_verifies_and_the_scan_then_shows_dose_and_use(client, world):
    """Verifying a catalogue row must unlock uses/dose on the scan card."""
    medicine = _add_catalogue_row(
        world,
        barcode=ean13("955123450003"),
        name="Ujian Sah 250 mg",
        verified=False,
        extra={"how_to_take": "Telan dengan segelas air.", "pack_size": "1 kotak = 10 tablet"},
    )
    signed = sign_in(client, world["users"]["owner_a"]["email"])

    page = client.get(f"/medicines/{medicine['id']}")
    assert "belum disahkan" in page.text
    assert "Sahkan maklumat ubat" in page.text

    response = client.post(
        f"/medicines/{medicine['id']}/verify",
        data={"csrf_token": csrf_token(page.text)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/medicines/{medicine['id']}"

    after = client.get(f"/medicines/{medicine['id']}")
    assert "Maklumat disahkan" in after.text
    assert "Sahkan maklumat ubat" not in after.text

    body = _scan(client, medicine["barcode"]).text
    assert "Dewasa: 1 tablet setiap 6 jam." in body
    assert "Mengurangkan sakit ringan." in body
    assert "Cara pengambilan" in body

    audit = signed.client.get("/usage")
    assert "medicine.verified" in audit.text


def test_only_the_owner_may_verify_a_medicine(client, world):
    """The pharmacist role has no feature permissions, so the action is refused."""
    medicine = _add_catalogue_row(
        world, barcode=ean13("955123450004"), name="Ujian Peranan 250 mg",
        verified=False, extra={},
    )
    sign_in(client, world["users"]["pharmacist_a"]["email"])
    page = client.get("/")
    assert page.status_code == 200

    response = client.post(
        f"/medicines/{medicine['id']}/verify",
        data={"csrf_token": csrf_token(page.text)},
    )

    assert response.status_code == 403
    assert db.find_medicine_by_barcode(
        world["conn"], world["tenants"]["a"], medicine["barcode"]
    )["verified"] == 0


def test_a_medicine_of_another_pharmacy_cannot_be_verified(client, world):
    medicine = _add_catalogue_row(
        world, barcode=ean13("955123450005"), name="Ujian Tenant 250 mg",
        verified=False, extra={},
    )
    sign_in(client, world["users"]["owner_b"]["email"])
    page = client.get("/")

    response = client.post(
        f"/medicines/{medicine['id']}/verify",
        data={"csrf_token": csrf_token(page.text)},
    )

    assert response.status_code == 404
    assert db.find_medicine_by_barcode(
        world["conn"], world["tenants"]["a"], medicine["barcode"]
    )["verified"] == 0
