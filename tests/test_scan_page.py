"""One page for scanning and finding: the scan page now owns "Cari Ubat" too.

The camera and the text box share a page, and the box accepts either a code or a
name. /search still answers (bookmarks, links in old pages) by showing the same
page, and /scan/lookup stays a strict barcode endpoint for the scanner.
"""
from __future__ import annotations

from tests.conftest import sign_in
from tests.helpers import count, csrf_token


def test_the_scan_page_has_one_box_for_code_or_name(client, world):
    sign_in(client, world["users"]["owner_a"]["email"])

    page = client.get("/scan")

    assert page.status_code == 200
    assert 'id="start-camera"' in page.text
    assert 'action="/scan/cari"' in page.text
    assert 'name="q"' in page.text
    assert "Imbas atau cari ubat" in page.text
    # One box only: no leftover second search form on the page.
    assert page.text.count("<form") == 2  # the search form + logout


def test_search_page_shows_the_same_merged_page(client, world):
    sign_in(client, world["users"]["owner_a"]["email"])

    search = client.get("/search")
    scan = client.get("/scan")

    assert search.status_code == 200
    assert 'id="start-camera"' in search.text
    assert 'action="/scan/cari"' in search.text
    # Same page, apart from which nav pill is highlighted.
    strip_nav = lambda html: html.split('class="nav"')[1].split("</nav>")[1]
    assert strip_nav(search.text) == strip_nav(scan.text)


def test_nav_has_one_entry_for_scanning_and_searching(client, world):
    sign_in(client, world["users"]["owner_a"]["email"])

    page = client.get("/")

    assert 'href="/scan"' in page.text
    assert "Imbas &amp; Cari" in page.text or "Imbas & Cari" in page.text
    assert 'href="/search"' not in page.text


def test_the_box_finds_a_medicine_by_name_without_saving_a_scan(client, world):
    medicine = world["medicines"]["a"][0]
    signed = sign_in(client, world["users"]["owner_a"]["email"])

    response = client.post(
        "/scan/cari",
        data={"q": medicine["name"].split()[0], "csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert 'data-lookup="found"' in response.text
    assert medicine["name"] in response.text
    assert count(world["conn"], "scans") == 0


def test_the_box_opens_the_detail_card_for_a_code_and_saves_the_scan(client, world):
    medicine = world["medicines"]["a"][0]
    signed = sign_in(client, world["users"]["owner_a"]["email"])

    response = client.post(
        "/scan/cari",
        data={"q": medicine["barcode"], "csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert 'data-scan="saved"' in response.text
    assert medicine["name"] in response.text
    assert count(world["conn"], "scans", world["tenants"]["a"]) == 1


def test_an_internal_code_from_a_qr_label_opens_the_card(client, world):
    signed = sign_in(client, world["users"]["owner_a"]["email"])
    medicine = world["medicines"]["a"][0]

    from app import db

    db.upsert_imported_medicine(
        world["conn"], world["tenants"]["a"],
        {
            "barcode": "C4C-7777", "name": "Ujian Kod Dalaman 100 mg",
            "brand": "", "active_ingredient": "Ujian", "strength": "100 mg",
            "dosage_form": "Tablet", "manufacturer": "", "uses": "",
            "dosage_instructions": "", "warnings": "", "side_effects": "",
            "storage": "", "category": "", "extra_json": "",
        },
    )
    world["conn"].commit()

    response = client.post(
        "/scan/cari",
        data={"q": "C4C-7777", "csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert 'data-scan="saved"' in response.text
    assert "Ujian Kod Dalaman 100 mg" in response.text
    assert medicine["name"] not in response.text


def test_a_blank_box_asks_for_input_without_saving(client, world):
    signed = sign_in(client, world["users"]["owner_a"]["email"])

    response = client.post(
        "/scan/cari",
        data={"q": "   ", "csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 422
    assert 'data-error="invalid_lookup"' in response.text
    assert count(world["conn"], "scans") == 0


def test_markup_in_the_box_is_escaped(client, world):
    signed = sign_in(client, world["users"]["owner_a"]["email"])

    response = client.post(
        "/scan/cari",
        data={"q": "<script>alert('x')</script>", "csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "<script>alert('x')</script>" not in response.text


def test_the_strict_scan_endpoint_still_refuses_a_bad_code(client, world):
    """The camera path stays strict: a bad read is an error, never a text search."""
    signed = sign_in(client, world["users"]["owner_a"]["email"])

    response = client.post(
        "/scan/lookup",
        data={"barcode": "abc", "csrf_token": signed.csrf},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 422
    assert 'data-error="invalid_barcode"' in response.text
    assert "Kod bar tidak sah" in response.text
