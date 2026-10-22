"""Test labels: scannable barcodes and QR codes for the catalogue."""
from __future__ import annotations

import pytest

from app.seed_data import ean13
from tests.conftest import sign_in
from tests.helpers import csrf_token

INTERNAL_CODE = "C4C-0424"


def test_svg_generators_produce_real_markup():
    from app import labels

    ean_svg = labels.barcode_svg("9550010000015")
    assert ean_svg.startswith("<svg")
    assert "DOCTYPE" not in ean_svg
    assert "<rect" in ean_svg or "<path" in ean_svg
    # No viewBox means CSS scaling stretches the bars into a black block.
    assert "viewBox=" in ean_svg
    assert "mm" not in ean_svg, "millimetres inside a px viewBox merge the bars"
    # CSP ignores inline style attributes, which would paint every bar black.
    assert "style=" not in ean_svg
    assert 'fill="white"' in ean_svg and 'fill="black"' in ean_svg

    internal_svg = labels.barcode_svg(INTERNAL_CODE)
    assert internal_svg.startswith("<svg")
    assert internal_svg != ean_svg

    qr_one = labels.qr_svg(INTERNAL_CODE)
    qr_two = labels.qr_svg("C4C-0425")
    assert qr_one.startswith("<svg") and qr_two.startswith("<svg")
    assert qr_one != qr_two

    # A Micro QR is much smaller but many phone scanners cannot read it.
    assert labels.qr_code("9550010000053").is_micro is False
    assert labels.qr_code(INTERNAL_CODE).is_micro is False

    assert labels.is_ean("9550010000015") is True
    assert labels.is_ean(INTERNAL_CODE) is False


def test_labels_page_shows_barcode_and_qr_for_each_medicine(client, world):
    total = len(world["medicines"]["a"])
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get("/labels/test")

    assert page.status_code == 200
    assert 'data-label="' in page.text
    assert page.text.count('class="label-card"') == min(24, total)
    assert page.text.count("<svg") >= 2 * min(24, total)  # barcode and QR per card

    ean = world["medicines"]["a"][0]["barcode"]
    assert f'data-label="{ean}"' in page.text
    assert "EAN-13" in page.text
    assert "kod QR" in page.text
    _ = signed


def test_labels_pagination(client, world):
    tenant_a = world["tenants"]["a"]
    for index in range(30):
        world["conn"].execute(
            "INSERT INTO medicines (tenant_id, barcode, name, created_at, updated_at) "
            "VALUES (?, ?, ?, '2026-10-22T00:00:00+00:00', '2026-10-22T00:00:00+00:00')",
            (tenant_a, ean13(f"955009{index:06d}"), f"Ubat Tambahan {index:02d}"),
        )
    world["conn"].commit()

    sign_in(client, world["users"]["owner_a"]["email"])
    first = client.get("/labels/test")
    second = client.get("/labels/test?page=2")
    assert second.status_code == 200
    assert "Halaman 2" in second.text
    assert second.text != first.text

    huge = client.get("/labels/test?page=999")
    assert huge.status_code == 200
    assert huge.text == client.get("/labels/test?page=2").text

    nonsense = client.get("/labels/test?page=abc")
    assert nonsense.status_code == 200
    assert "label-card" in nonsense.text


@pytest.mark.parametrize("role", ["pharmacist_a", "guest_a", "admin_a"])
def test_labels_page_needs_the_scan_permission(client, world, role):
    sign_in(client, world["users"][role]["email"])
    page = client.get("/labels/test", follow_redirects=False)
    assert page.status_code == 403
    assert 'data-error="forbidden"' in page.text


def test_labels_page_is_not_public(client):
    page = client.get("/labels/test", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"].startswith("/login")


def test_scanning_an_internal_code_from_a_qr_label(client, world):
    """A QR label carries the product code; the catalogue checkout finds it."""
    tenant_a = world["tenants"]["a"]
    world["conn"].execute(
        "INSERT INTO medicines (tenant_id, barcode, name, strength, verified, created_at, updated_at) "
        "VALUES (?, ?, 'Ubat Kod Dalaman', '10 mg', 0, '2026-10-22T00:00:00+00:00', '2026-10-22T00:00:00+00:00')",
        (tenant_a, INTERNAL_CODE),
    )
    world["conn"].commit()

    signed = sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get("/scan")
    response = client.post(
        "/scan/lookup",
        data={"barcode": INTERNAL_CODE, "request_id": "qr-label-1", "csrf_token": csrf_token(page.text)},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200, response.text
    assert 'data-scan="saved"' in response.text
    assert "Ubat Kod Dalaman" in response.text

    saved = world["conn"].execute(
        "SELECT barcode, found FROM scans WHERE tenant_id = ? ORDER BY id DESC LIMIT 1", (tenant_a,)
    ).fetchone()
    assert saved["barcode"] == INTERNAL_CODE
    assert saved["found"] == 1
    _ = signed


def test_scanning_accepts_a_lowercase_internal_code(client, world):
    tenant_a = world["tenants"]["a"]
    world["conn"].execute(
        "INSERT INTO medicines (tenant_id, barcode, name, created_at, updated_at) "
        "VALUES (?, 'C4C-0777', 'Ubat Huruf Kecil', '2026-10-22T00:00:00+00:00', '2026-10-22T00:00:00+00:00')",
        (tenant_a,),
    )
    world["conn"].commit()

    signed = sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get("/scan")
    response = client.post(
        "/scan/lookup",
        data={"barcode": "c4c-0777", "csrf_token": csrf_token(page.text)},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Ubat Huruf Kecil" in response.text
    _ = signed


def test_unknown_code_is_still_refused(client, world):
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get("/scan")
    response = client.post(
        "/scan/lookup",
        data={"barcode": "ZZZ-9999", "csrf_token": csrf_token(page.text)},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 422
    assert 'data-error="invalid_barcode"' in response.text
    assert world["conn"].execute("SELECT COUNT(*) FROM scans").fetchone()[0] == 0
    _ = signed


def test_qr_label_matches_a_scannable_ean(client, world):
    """The EAN printed on a label is the same value the camera posts."""
    from app import labels

    medicine = world["medicines"]["a"][1]
    item = labels.label_item(medicine)
    assert item["code"] == medicine["barcode"]
    assert item["kind"] == "EAN-13"

    signed = sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get(f"/medicines/{medicine['id']}")
    assert page.status_code == 200
    scan_page = client.get("/scan")
    response = client.post(
        "/scan/lookup",
        data={"barcode": item["code"], "csrf_token": csrf_token(scan_page.text)},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert medicine["name"] in response.text
    _ = signed


def test_labels_include_the_imported_catalogue(client, world):
    """Imported internal codes get a Code 128 label and a QR."""
    tenant_a = world["tenants"]["a"]
    for code in (ean13("955001000905"), "C4C-0001"):
        world["conn"].execute(
            "INSERT INTO medicines (tenant_id, barcode, name, created_at, updated_at) "
            "VALUES (?, ?, ?, '2026-10-22T00:00:00+00:00', '2026-10-22T00:00:00+00:00')",
            (tenant_a, code, f"Ubat {code}"),
        )
    world["conn"].commit()

    sign_in(client, world["users"]["owner_a"]["email"])
    page = client.get("/labels/test")
    assert page.status_code == 200
    assert 'data-label="C4C-0001"' in page.text
    assert "Code 128" in page.text
